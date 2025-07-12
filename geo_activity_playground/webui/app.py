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

import pandas as pd
import sqlalchemy
from flask import Config
from flask import Flask
from flask import request
from flask_alembic import Alembic

from ..core.activities import ActivityRepository
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
from ..core.raster_map import GrayscaleImageTransform
from ..core.raster_map import IdentityImageTransform
from ..core.raster_map import InverseGrayscaleImageTransform
from ..core.raster_map import PastelImageTransform
from ..core.raster_map import TileGetter
from ..explorer.tile_visits import TileVisitAccessor
from .authenticator import Authenticator
from .blueprints.activity_blueprint import make_activity_blueprint
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
from .blueprints.settings_blueprint import make_settings_blueprint
from .blueprints.square_planner_blueprint import make_square_planner_blueprint
from .blueprints.summary_blueprint import make_summary_blueprint
from .blueprints.tile_blueprint import make_tile_blueprint
from .blueprints.time_zone_fixer_blueprint import make_time_zone_fixer_blueprint
from .blueprints.upload_blueprint import make_upload_blueprint
from .blueprints.upload_blueprint import scan_for_activities
from .flasher import FlaskFlasher
from .search_util import SearchQueryHistory


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
) -> None:
    with app.app_context():
        scan_for_activities(repository, tile_visit_accessor, config)
    logger.info("Importer thread is done.")


def web_ui_main(
    basedir: pathlib.Path,
    skip_reload: bool,
    host: str,
    port: int,
) -> None:
    os.chdir(basedir)

    warnings.filterwarnings("ignore", "__array__ implementation doesn't")
    warnings.filterwarnings("ignore", '\'field "native_field_num"')
    warnings.filterwarnings("ignore", '\'field "units"')
    warnings.filterwarnings(
        "ignore", r"datetime.datetime.utcfromtimestamp\(\) is deprecated"
    )
    app = Flask(__name__)

    database_path = pathlib.Path("database.sqlite")
    logger.info(f"Using database file at '{database_path.absolute()}'.")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path.absolute()}"
    app.config["ALEMBIC"] = {"script_location": "../alembic/versions"}
    DB.init_app(app)

    alembic = Alembic()
    alembic.init_app(app)

    with app.app_context():
        alembic.upgrade()
        DB.session.commit()
        # DB.create_all()

    repository = ActivityRepository()
    tile_visit_accessor = TileVisitAccessor()
    config_accessor = ConfigAccessor()
    import_old_config(config_accessor)
    import_old_strava_config(config_accessor)

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
        thread = threading.Thread(
            target=importer_thread,
            args=(app, repository, tile_visit_accessor, config_accessor()),
        )
        thread.start()

    app.config["UPLOAD_FOLDER"] = "Activities"
    app.secret_key = get_secret_key()

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
        if pd.isna(v):
            return "—"
        else:
            seconds = v.total_seconds()
            h = int(seconds // 3600)
            m = int(seconds // 60 % 60)
            s = int(seconds // 1 % 60)
            return f"{h}:{m:02d}:{s:02d}"

    @app.template_filter()
    def isna(value):
        return pd.isna(value)

    authenticator = Authenticator(config_accessor())
    search_query_history = SearchQueryHistory(config_accessor, authenticator)
    config = config_accessor()
    tile_getter = TileGetter(config.map_tile_url)
    image_transforms = {
        "color": IdentityImageTransform(),
        "grayscale": GrayscaleImageTransform(),
        "pastel": PastelImageTransform(),
        "inverse_grayscale": InverseGrayscaleImageTransform(),
    }
    flasher = FlaskFlasher()
    heart_rate_zone_computer = HeartRateZoneComputer(config)

    register_entry_views(app, repository, config)

    blueprints = {
        "/activity": make_activity_blueprint(
            repository,
            authenticator,
            tile_visit_accessor,
            config,
            heart_rate_zone_computer,
        ),
        "/auth": make_auth_blueprint(authenticator),
        "/bubble-chart": make_bubble_chart_blueprint(repository),
        "/calendar": make_calendar_blueprint(repository),
        "/eddington": register_eddington_blueprint(repository, search_query_history),
        "/equipment": make_equipment_blueprint(repository, config),
        "/explorer": make_explorer_blueprint(
            authenticator,
            tile_visit_accessor,
            config_accessor,
            tile_getter,
            image_transforms,
        ),
        "/export": make_export_blueprint(authenticator),
        "/hall-of-fame": make_hall_of_fame_blueprint(repository, search_query_history),
        "/heatmap": make_heatmap_blueprint(
            repository, tile_visit_accessor, config_accessor(), search_query_history
        ),
        "/photo": make_photo_blueprint(config_accessor, authenticator, flasher),
        "/plot-builder": make_plot_builder_blueprint(
            repository, flasher, authenticator
        ),
        "/settings": make_settings_blueprint(config_accessor, authenticator, flasher),
        "/square-planner": make_square_planner_blueprint(tile_visit_accessor),
        "/search": make_search_blueprint(
            repository, search_query_history, authenticator, config_accessor
        ),
        "/summary": make_summary_blueprint(repository, config, search_query_history),
        "/tile": make_tile_blueprint(image_transforms, tile_getter),
        "/time-zone-fixer": make_time_zone_fixer_blueprint(
            authenticator, config, tile_visit_accessor
        ),
        "/upload": make_upload_blueprint(
            repository, tile_visit_accessor, config_accessor(), authenticator, flasher
        ),
    }

    for url_prefix, blueprint in blueprints.items():
        app.register_blueprint(blueprint, url_prefix=url_prefix)

    base_dir = pathlib.Path("Open Street Map Tiles")
    dir_for_source = base_dir / urllib.parse.quote_plus(config_accessor().map_tile_url)
    if base_dir.exists() and not dir_for_source.exists():
        subdirs = base_dir.glob("*")
        dir_for_source.mkdir()
        for subdir in subdirs:
            shutil.move(subdir, dir_for_source)

    @app.context_processor
    def inject_global_variables() -> dict:
        variables = {
            "version": _try_get_version(),
            "num_activities": len(repository),
            "map_tile_attribution": config_accessor().map_tile_attribution,
            # "search_query_favorites": search_query_history.prepare_favorites(),
            # "search_query_last": search_query_history.prepare_last(),
            "request_url": urllib.parse.quote_plus(request.url),
            "host_url": request.host_url,
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

    app.run(host=host, port=port)


def _try_get_version():
    try:
        return importlib.metadata.version("geo-activity-playground")
    except importlib.metadata.PackageNotFoundError:
        pass
