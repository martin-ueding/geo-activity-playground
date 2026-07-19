import atexit
import datetime
import html
import importlib
import importlib.metadata
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
import webbrowser
from collections.abc import Iterable
from typing import Any, Literal
from wsgiref.types import StartResponse, WSGIApplication, WSGIEnvironment

import markdown
import pandas as pd
import sqlalchemy
import waitress
from flask import Flask, request
from flask_alembic import Alembic
from flask_babel import Babel
from markupsafe import Markup

from ..core.activities import ActivityRepository
from ..core.config import ConfigAccessor, import_config_json
from ..core.datamodel import (
    DB,
    DEFAULT_UNKNOWN_NAME,
    Activity,
    Equipment,
    Kind,
    Tag,
)
from ..core.heart_rate import HeartRateZoneComputer
from ..core.paths import TIME_SERIES_DIR
from ..core.raster_map import (
    BlankImageTransform,
    GrayscaleImageTransform,
    IdentityImageTransform,
    InverseGrayscaleImageTransform,
    PastelImageTransform,
    TileGetter,
)
from ..core.scan import scan_for_activities
from ..features.activity.blueprint import make_activity_blueprint
from ..features.activity_photos.blueprint import make_photo_blueprint
from ..features.activity_photos.model import Photo
from ..features.authentication.blueprint import make_authentication_blueprint
from ..features.bubble_chart.blueprint import make_bubble_chart_blueprint
from ..features.calendar.blueprint import make_calendar_blueprint
from ..features.data_export.blueprint import make_export_blueprint
from ..features.eddington.blueprint import register_eddington_blueprint
from ..features.equipment.blueprint import make_equipment_blueprint
from ..features.explorer_video.video_blueprint import make_explorer_video_blueprint
from ..features.hall_of_fame.blueprint import make_hall_of_fame_blueprint
from ..features.hammerhead.model import get_hammerhead_auth
from ..features.heatmap.blueprint import make_heatmap_blueprint
from ..features.heatmap.cache import (
    delete_small_heatmap_cache_entries,
    import_legacy_heatmap_cache_from_filesystem,
)
from ..features.heatmap.model import HeatmapTileCache  # noqa: F401
from ..features.plot_builder.blueprint import make_plot_builder_blueprint
from ..features.plot_builder.model import PlotSpec  # noqa: F401
from ..features.segments.blueprint import make_segments_blueprint
from ..features.segments.model import Segment  # noqa: F401
from ..features.sharepic.blueprint import make_sharepic_blueprint
from ..features.shutdown.blueprint import make_shutdown_blueprint
from ..features.square_planner.blueprint import make_square_planner_blueprint
from ..features.square_planner.model import SquarePlannerBookmark  # noqa: F401
from ..features.summary.blueprint import make_summary_blueprint
from ..features.tile.blueprint import make_tile_blueprint
from ..features.upload.blueprint import make_upload_blueprint
from .authenticator import Authenticator
from .blueprints.entry_views import register_entry_views
from .blueprints.explorer_blueprint import make_explorer_blueprint
from .blueprints.search_blueprint import make_search_blueprint
from .blueprints.settings_blueprint import make_settings_blueprint
from .flasher import FlaskFlasher
from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGE_CODES

logger = logging.getLogger(__name__)


def _without_response_header(
    application: WSGIApplication, header_name: str
) -> WSGIApplication:
    """Wrap a WSGI app and remove one response header by name."""

    header_name_lower = header_name.lower()

    def wrapped_application(
        environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        def filtered_start_response(status, headers, exc_info=None):
            filtered_headers = [
                (name, value)
                for name, value in headers
                if name.lower() != header_name_lower
            ]
            return start_response(status, filtered_headers, exc_info)

        return application(environ, filtered_start_response)

    return wrapped_application


def _migrate_null_activity_fields_to_unknown() -> None:
    activities = DB.session.scalars(
        sqlalchemy.select(Activity).where(
            sqlalchemy.or_(
                Activity.kind_id.is_(None),
                Activity.equipment_id.is_(None),
            )
        )
    ).all()
    if not activities:
        return

    unknown_kind = DB.session.scalar(
        sqlalchemy.select(Kind).where(Kind.name == DEFAULT_UNKNOWN_NAME)
    )
    if unknown_kind is None:
        unknown_kind = Kind(name=DEFAULT_UNKNOWN_NAME, consider_for_achievements=True)
        DB.session.add(unknown_kind)

    unknown_equipment = DB.session.scalar(
        sqlalchemy.select(Equipment).where(Equipment.name == DEFAULT_UNKNOWN_NAME)
    )
    if unknown_equipment is None:
        unknown_equipment = Equipment(name=DEFAULT_UNKNOWN_NAME)
        DB.session.add(unknown_equipment)

    for activity in activities:
        if activity.kind is None:
            activity.kind = unknown_kind
        if activity.equipment is None:
            activity.equipment = unknown_equipment

    if activities:
        logger.info(
            "Migrated %d activities with NULL kind/equipment to '%s'.",
            len(activities),
            DEFAULT_UNKNOWN_NAME,
        )
    DB.session.commit()


def _migrate_hammerhead_credentials_to_db() -> None:
    config_path = pathlib.Path("config.json")
    if not config_path.exists():
        return
    with open(config_path) as f:
        raw = json.load(f)
    old_fields = {
        "hammerhead_client_id",
        "hammerhead_client_secret",
        "hammerhead_client_code",
    }
    if not any(k in raw for k in old_fields):
        return
    client_id: str | None = raw.get("hammerhead_client_id")
    client_secret: str | None = raw.get("hammerhead_client_secret")
    client_code: str | None = raw.get("hammerhead_client_code")
    auth = get_hammerhead_auth()
    if client_id and not auth.client_id:
        auth.client_id = client_id
    if client_secret and not auth.client_secret:
        auth.client_secret = client_secret
    if client_code and not auth.client_code:
        auth.client_code = client_code
    DB.session.commit()
    for key in old_fields:
        raw.pop(key, None)
    with open(config_path, "w") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2, sort_keys=True)
    logger.info("Migrated Hammerhead credentials from config.json to database.")


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


def create_app(
    database_uri: str = "sqlite:///database.sqlite",
    secret_key: str | None = None,
    run_migrations: bool = True,
    http_server: Literal["waitress", "werkzeug", "gunicorn"] | None = None,
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
    if database_uri.startswith("sqlite:///") and database_uri != "sqlite:///:memory:":
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"timeout": 30},
        }
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

        # Check stored user preference.
        preferred_language = config_accessor.ui().preferred_language
        if preferred_language:
            if preferred_language in app.config["BABEL_SUPPORTED_LOCALES"]:
                return preferred_language

        # Fall back to browser's preferred language
        return request.accept_languages.best_match(
            app.config["BABEL_SUPPORTED_LOCALES"]
        )

    Babel(app, locale_selector=get_locale)

    DB.init_app(app)

    if database_uri.startswith("sqlite:///") and database_uri != "sqlite:///:memory:":
        with app.app_context():

            @sqlalchemy.event.listens_for(DB.engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

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
    config_accessor = ConfigAccessor()
    with app.app_context():
        # Seed a fresh database from a legacy config.json before filling in any
        # remaining defaults; import_config_json is a no-op once rows exist.
        import_config_json(config_accessor)
        config_accessor.ensure_exists()
        _migrate_null_activity_fields_to_unknown()
        import_legacy_heatmap_cache_from_filesystem()
        delete_small_heatmap_cache_entries(
            config_accessor.ui().heatmap_cache_min_activities
        )
        map_tile_url = config_accessor.map().map_tile_url

    authenticator = Authenticator(config_accessor)
    tile_getter = TileGetter(map_tile_url)
    image_transforms = {
        "color": IdentityImageTransform(),
        "grayscale": GrayscaleImageTransform(),
        "pastel": PastelImageTransform(),
        "inverse_grayscale": InverseGrayscaleImageTransform(),
        "blank": BlankImageTransform(),
    }
    flasher = FlaskFlasher()
    heart_rate_zone_computer = HeartRateZoneComputer(config_accessor)

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

    @app.template_filter()
    def render_markdown(text: str | None) -> Markup:
        if not text:
            return Markup("")
        escaped = html.escape(text, quote=False)
        return Markup(markdown.markdown(escaped, extensions=["nl2br"]))

    # Register routes and blueprints
    register_entry_views(app, repository, config_accessor)

    blueprints = [
        (
            "/activity",
            make_activity_blueprint(
                repository,
                authenticator,
                config_accessor,
                heart_rate_zone_computer,
            ),
        ),
        (
            "/authentication",
            make_authentication_blueprint(authenticator, config_accessor, flasher),
        ),
        ("/bubble-chart", make_bubble_chart_blueprint(repository)),
        ("/calendar", make_calendar_blueprint(repository, config_accessor)),
        ("/eddington", register_eddington_blueprint(repository, authenticator)),
        ("/equipment", make_equipment_blueprint(repository, config_accessor)),
        (
            "/explorer",
            make_explorer_blueprint(
                authenticator,
                config_accessor,
                tile_getter,
                image_transforms,
            ),
        ),
        ("/explorer", make_explorer_video_blueprint(authenticator, config_accessor)),
        ("/export", make_export_blueprint(authenticator)),
        (
            "/hall-of-fame",
            make_hall_of_fame_blueprint(repository, authenticator, config_accessor),
        ),
        (
            "/heatmap",
            make_heatmap_blueprint(repository, config_accessor, authenticator),
        ),
        ("/photo", make_photo_blueprint(config_accessor, authenticator, flasher)),
        (
            "/plot-builder",
            make_plot_builder_blueprint(repository, flasher, authenticator),
        ),
        (
            "/settings",
            make_settings_blueprint(
                config_accessor, authenticator, flasher, repository
            ),
        ),
        (
            "/segments",
            make_segments_blueprint(authenticator, flasher, config_accessor),
        ),
        (
            "/sharepic",
            make_sharepic_blueprint(repository, config_accessor),
        ),
        (
            "/shutdown",
            make_shutdown_blueprint(
                authenticator, multi_process=http_server == "gunicorn"
            ),
        ),
        ("/square-planner", make_square_planner_blueprint()),
        ("/search", make_search_blueprint(authenticator, config_accessor)),
        (
            "/summary",
            make_summary_blueprint(repository, config_accessor, authenticator),
        ),
        ("/tile", make_tile_blueprint(image_transforms, tile_getter)),
        (
            "/upload",
            make_upload_blueprint(repository, config_accessor, authenticator, flasher),
        ),
    ]

    for url_prefix, blueprint in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)

    # Register context processor for global template variables
    @app.context_processor
    def inject_global_variables() -> dict:
        variables = {
            "version": _try_get_version(),
            "num_activities": len(repository),
            "map_tile_attribution": config_accessor.map().map_tile_attribution,
            "request_url": urllib.parse.quote_plus(request.url),
            "explorer_zoom_levels": sorted(config_accessor.ui().explorer_zoom_levels)
            or [14],
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

    app.activity_repository = repository

    return app


def web_ui_main(
    basedir: pathlib.Path,
    skip_reload: bool,
    host: str,
    port: int,
    strava_begin: str | None,
    strava_end: str | None,
    hammerhead_begin: str | None = None,
    hammerhead_end: str | None = None,
    http_server: Literal["waitress", "werkzeug", "gunicorn"] = "gunicorn",
    threads: int = 8,
    workers: int = 4,
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
        http_server=http_server,
    )

    # Settings are seeded from any legacy config.json inside create_app().
    config_accessor = ConfigAccessor()

    # Migrate Hammerhead credentials from config.json to database
    with app.app_context():
        _migrate_hammerhead_credentials_to_db()

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

    if not skip_reload:
        repository = app.activity_repository
        with app.app_context():
            scan_for_activities(
                repository,
                config_accessor,
                strava_begin=strava_begin,
                strava_end=strava_end,
                hammerhead_begin=hammerhead_begin,
                hammerhead_end=hammerhead_end,
            )

    # Migrate Photos/original/ → Photos/ (flatten inbox structure)
    photos_original = pathlib.Path("Photos/original")
    if photos_original.exists():
        for f in photos_original.iterdir():
            dest = pathlib.Path("Photos") / f.name
            if not dest.exists():
                f.rename(dest)
        try:
            photos_original.rmdir()
        except OSError:
            pass
        logger.info("Migrated Photos/original/ to Photos/")

    # Migrate Photos/size-*/ thumbnail caches to Cache/Photos/
    for old_cache in pathlib.Path("Photos").glob("size-*"):
        if old_cache.is_dir():
            dest = pathlib.Path("Cache") / "Photos" / old_cache.name
            dest.parent.mkdir(exist_ok=True, parents=True)
            old_cache.rename(dest)

    # Migrate tile cache directory structure
    base_dir = pathlib.Path("Open Street Map Tiles")
    with app.app_context():
        map_tile_url = config_accessor.map().map_tile_url
    dir_for_source = base_dir / urllib.parse.quote_plus(map_tile_url)
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

    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browser_host}:{port}"

    def open_browser() -> None:
        try:
            webbrowser.open(url)
        except webbrowser.Error as e:
            logger.debug("Could not open browser: %s", e)

    threading.Timer(3.0, open_browser).start()

    if http_server == "waitress":
        logger.info(
            "Starting Waitress server at http://%s:%d with %d threads",
            host,
            port,
            threads,
        )
        waitress_application = _without_response_header(app, "Date")
        waitress.serve(
            waitress_application,
            host=host,
            port=port,
            asyncore_use_poll=True,
            threads=threads,
        )
    elif http_server == "gunicorn":
        from gunicorn.app.base import BaseApplication

        class _GunicornApp(BaseApplication):
            def load_config(self) -> None:
                self.cfg.set("bind", f"{host}:{port}")
                self.cfg.set("workers", workers)
                self.cfg.set("worker_class", "gthread")
                self.cfg.set("threads", threads)
                self.cfg.set("preload_app", True)

            def load(self) -> Any:
                return app

        logger.info(
            "Starting Gunicorn server at http://%s:%d with %d workers × %d threads",
            host,
            port,
            workers,
            threads,
        )
        _GunicornApp().run()
    else:
        logger.info("Starting Werkzeug development server at http://%s:%d", host, port)
        app.run(host=host, port=port)


def _try_get_version():
    try:
        return importlib.metadata.version("geo-activity-playground")
    except importlib.metadata.PackageNotFoundError:
        pass
