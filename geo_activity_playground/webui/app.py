import atexit
import datetime
import importlib
import json
import logging
import os
import pathlib
import secrets
import shutil
import sys
import threading
import urllib.parse
import uuid
import warnings
from typing import Optional

import pandas as pd
import sqlalchemy
from flask import Flask
from flask import request
from flask_alembic import Alembic
from flask_babel import Babel

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.config import ConfigAccessor
from ..core.config import import_old_config
from ..core.config import import_old_strava_config
from ..core.datamodel import Activity
from ..core.datamodel import DB
from ..core.datamodel import Equipment
from ..core.datamodel import Kind
from ..core.datamodel import Photo
from ..core.datamodel import Tag
from ..core.heart_rate import HeartRateZoneComputer
from ..core.paths import TIME_SERIES_DIR
from ..core.raster_map import BlankImageTransform
from ..core.raster_map import GrayscaleImageTransform
from ..core.raster_map import IdentityImageTransform
from ..core.raster_map import InverseGrayscaleImageTransform
from ..core.raster_map import PastelImageTransform
from ..core.raster_map import TileGetter
from ..explorer.tile_visits import TileVisitAccessor
from .authenticator import Authenticator
from .i18n import DEFAULT_LANGUAGE
from .i18n import SUPPORTED_LANGUAGE_CODES
from .i18n import SUPPORTED_LANGUAGES
from .blueprints.activity_blueprint import make_activity_blueprint
from .blueprints.admin_blueprint import make_admin_blueprint
from .blueprints.auth_blueprint import make_auth_blueprint
from .blueprints.bubble_chart_blueprint import make_bubble_chart_blueprint
from .blueprints.calendar_blueprint import make_calendar_blueprint
from .blueprints.eddington_blueprints import register_eddington_blueprint
from .blueprints.entry_views import register_entry_views
from .blueprints.equipment_blueprint import make_equipment_blueprint
from .blueprints.explorer_blueprint import make_explorer_blueprint
from .blueprints.export_blueprint import make_export_blueprint
from .blueprints.hall_of_fame_blueprint import make_hall_of_fame_blueprint
from .blueprints.heatmap_blueprint import make_heatmap_blueprint
from .blueprints.photo_blueprint import make_photo_blueprint
from .blueprints.plot_builder_blueprint import make_plot_builder_blueprint
from .blueprints.search_blueprint import make_search_blueprint
from .blueprints.segments_blueprint import make_segments_blueprint
from .blueprints.settings_blueprint import make_settings_blueprint
from .blueprints.square_planner_blueprint import make_square_planner_blueprint
from .blueprints.summary_blueprint import make_summary_blueprint
from .blueprints.tile_blueprint import make_tile_blueprint
from .blueprints.time_zone_fixer_blueprint import make_time_zone_fixer_blueprint
from .blueprints.upload_blueprint import make_upload_blueprint
from .blueprints.upload_blueprint import scan_for_activities
from .flasher import FlaskFlasher


logger = logging.getLogger(__name__)


def get_secret_key():
    secret_file = pathlib.Path("Cache/flask-secret.json")
    if secret_file.exists():
        with open(secret_file) as f:
            secret = json.load(f)
    else:
        secret = secrets.token_hex()
        secret_file.parent.mkdir(exist_ok=True, parents=True)
        with open(secret_file, "w") as f:
            json.dump(secret, f)
    return secret


def importer_thread(
    app: Flask,
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    strava_begin: Optional[str],
    strava_end: Optional[str],
) -> None:
    with app.app_context():
        scan_for_activities(
            repository, tile_visit_accessor, config, strava_begin, strava_end
        )
    logger.info("Importer thread is done.")


def create_app(
    database_uri: str = "sqlite:///database.sqlite",
    secret_key: Optional[str] = None,
    run_migrations: bool = True,
) -> Flask:
    """
    Create and configure the Flask application.

    This is the application factory that can be used by both production
    code and tests.

    Args:
        database_uri: SQLAlchemy database URI. Use "sqlite:///:memory:" for tests.
        secret_key: Flask secret key. If None, will be generated/loaded from file.
        run_migrations: If True, run Alembic migrations. If False, use DB.create_all().
                       Set to False for tests to speed up setup.

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["UPLOAD_FOLDER"] = "Activities"
    app.secret_key = secret_key or get_secret_key()

    # Configure Babel for internationalization
    app.config["BABEL_DEFAULT_LOCALE"] = DEFAULT_LANGUAGE
    app.config["BABEL_SUPPORTED_LOCALES"] = SUPPORTED_LANGUAGE_CODES
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

    def get_locale():
        # Try to get locale from query parameter first (for testing)
        if "lang" in request.args:
            lang = request.args.get("lang")
            if lang in app.config["BABEL_SUPPORTED_LOCALES"]:
                return lang
        
        # Check config file for user preference
        if config.preferred_language:
            if config.preferred_language in app.config["BABEL_SUPPORTED_LOCALES"]:
                return config.preferred_language
        
        # Fall back to browser's preferred language
        return request.accept_languages.best_match(
            app.config["BABEL_SUPPORTED_LOCALES"]
        )

    babel = Babel(app, locale_selector=get_locale)

    DB.init_app(app)

    if run_migrations:
        app.config["ALEMBIC"] = {"script_location": "../alembic/versions"}
        alembic = Alembic()
        alembic.init_app(app)
        with app.app_context():
            alembic.upgrade()
            DB.session.commit()
    else:
        with app.app_context():
            DB.create_all()

    # Set up dependencies
    repository = ActivityRepository()
    tile_visit_accessor = TileVisitAccessor()
    # Complete any pending migration from old pickle format (requires app context)
    with app.app_context():
        tile_visit_accessor.complete_migration()
    config_accessor = ConfigAccessor()
    config = config_accessor()

    authenticator = Authenticator(config)
    tile_getter = TileGetter(config.map_tile_url)
    image_transforms = {
        "color": IdentityImageTransform(),
        "grayscale": GrayscaleImageTransform(),
        "pastel": PastelImageTransform(),
        "inverse_grayscale": InverseGrayscaleImageTransform(),
        "blank": BlankImageTransform(),
    }
    flasher = FlaskFlasher()
    heart_rate_zone_computer = HeartRateZoneComputer(config)

    # Register template filters
    @app.template_filter()
    def dt(value: datetime.datetime):
        if pd.isna(value):
            return "—"
        else:
            return value.strftime("%Y-%m-%d %H:%M")

    @app.template_global("unique_id")
    def unique_id():
        return f"id-{uuid.uuid4()}"

    @app.template_filter()
    def td(v: datetime.timedelta):
        if pd.isna(v) or v is None:
            return "—"
        else:
            seconds = v.total_seconds()
            h = int(seconds // 3600)
            m = int(seconds // 60 % 60)
            s = int(seconds // 1 % 60)
            return f"{h}:{m:02d}:{s:02d}"

    @app.template_filter()
    def abs_td(v: datetime.timedelta):
        """Format timedelta as absolute value (ignoring direction)."""
        return td(abs(v) if v is not None and not pd.isna(v) else v)

    @app.template_filter()
    def isna(value):
        return pd.isna(value)

    # Register routes and blueprints
    register_entry_views(app, repository, config)

    blueprints = {
        "/activity": make_activity_blueprint(
            repository,
            authenticator,
            tile_visit_accessor,
            config,
            heart_rate_zone_computer,
        ),
        "/admin": make_admin_blueprint(authenticator),
        "/auth": make_auth_blueprint(authenticator),
        "/bubble-chart": make_bubble_chart_blueprint(repository),
        "/calendar": make_calendar_blueprint(repository),
        "/eddington": register_eddington_blueprint(repository, authenticator),
        "/equipment": make_equipment_blueprint(repository, config),
        "/explorer": make_explorer_blueprint(
            authenticator,
            tile_visit_accessor,
            config_accessor,
            tile_getter,
            image_transforms,
            config,
        ),
        "/export": make_export_blueprint(authenticator),
        "/hall-of-fame": make_hall_of_fame_blueprint(repository, authenticator),
        "/heatmap": make_heatmap_blueprint(
            repository, tile_visit_accessor, config, authenticator
        ),
        "/photo": make_photo_blueprint(config_accessor, authenticator, flasher),
        "/plot-builder": make_plot_builder_blueprint(
            repository, flasher, authenticator
        ),
        "/settings": make_settings_blueprint(config_accessor, authenticator, flasher),
        "/segments": make_segments_blueprint(
            authenticator, tile_visit_accessor, flasher, config
        ),
        "/square-planner": make_square_planner_blueprint(tile_visit_accessor),
        "/search": make_search_blueprint(authenticator),
        "/summary": make_summary_blueprint(repository, config, authenticator),
        "/tile": make_tile_blueprint(image_transforms, tile_getter),
        "/time-zone-fixer": make_time_zone_fixer_blueprint(
            authenticator, config, tile_visit_accessor
        ),
        "/upload": make_upload_blueprint(
            repository, tile_visit_accessor, config, authenticator, flasher
        ),
    }

    for url_prefix, blueprint in blueprints.items():
        app.register_blueprint(blueprint, url_prefix=url_prefix)

    # Register context processor for global template variables
    @app.context_processor
    def inject_global_variables() -> dict:
        variables = {
            "version": _try_get_version(),
            "num_activities": len(repository),
            "map_tile_attribution": config_accessor().map_tile_attribution,
            "request_url": urllib.parse.quote_plus(request.url),
        }
        variables["equipments_avail"] = DB.session.scalars(
            sqlalchemy.select(Equipment).order_by(Equipment.name)
        ).all()
        variables["kinds_avail"] = DB.session.scalars(
            sqlalchemy.select(Kind).order_by(Kind.name)
        ).all()
        variables["tags_avail"] = DB.session.scalars(
            sqlalchemy.select(Tag).order_by(Tag.tag)
        ).all()
        variables["photo_count"] = DB.session.scalar(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(Photo)
        )
        variables["python_version"] = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
        return variables

    return app


def web_ui_main(
    basedir: pathlib.Path,
    skip_reload: bool,
    host: str,
    port: int,
    strava_begin: Optional[str],
    strava_end: Optional[str],
) -> None:
    os.chdir(basedir)

    warnings.filterwarnings("ignore", "__array__ implementation doesn't")
    warnings.filterwarnings("ignore", '\'field "native_field_num"')
    warnings.filterwarnings("ignore", '\'field "units"')
    warnings.filterwarnings(
        "ignore", r"datetime.datetime.utcfromtimestamp\(\) is deprecated"
    )

    database_path = pathlib.Path("database.sqlite")
    logger.info(f"Using database file at '{database_path.absolute()}'.")

    app = create_app(
        database_uri=f"sqlite:///{database_path.absolute()}",
        run_migrations=True,
    )

    # Import old config formats
    config_accessor = ConfigAccessor()
    import_old_config(config_accessor)
    import_old_strava_config(config_accessor)

    # Migrate time series files to new UUID-based naming
    with app.app_context():
        for activity in DB.session.scalars(sqlalchemy.select(Activity)).all():
            if not activity.time_series_uuid:
                activity.time_series_uuid = str(uuid.uuid4())
                DB.session.commit()
            old_path = TIME_SERIES_DIR() / f"{activity.id}.parquet"
            if old_path.exists() and not activity.time_series_path.exists():
                old_path.rename(activity.time_series_path)
            if not activity.time_series_path.exists():
                logger.error(
                    f"Time series for {activity.id=}, expected at {activity.time_series_path}, does not exist. Deleting activity."
                )
                DB.session.delete(activity)
                DB.session.commit()

    # Start background importer thread
    if not skip_reload:
        repository = ActivityRepository()
        tile_visit_accessor = TileVisitAccessor()
        thread = threading.Thread(
            target=importer_thread,
            args=(
                app,
                repository,
                tile_visit_accessor,
                config_accessor(),
                strava_begin,
                strava_end,
            ),
        )
        thread.start()

    # Migrate tile cache directory structure
    base_dir = pathlib.Path("Open Street Map Tiles")
    dir_for_source = base_dir / urllib.parse.quote_plus(config_accessor().map_tile_url)
    if base_dir.exists() and not dir_for_source.exists():
        subdirs = base_dir.glob("*")
        dir_for_source.mkdir()
        for subdir in subdirs:
            shutil.move(subdir, dir_for_source)

    # Register cleanup handler to properly close database connection on shutdown
    def cleanup():
        with app.app_context():
            DB.engine.dispose()

    atexit.register(cleanup)

    app.run(host=host, port=port)


def _try_get_version():
    try:
        return importlib.metadata.version("geo-activity-playground")
    except importlib.metadata.PackageNotFoundError:
        pass
