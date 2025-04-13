import datetime
import importlib
import json
import pathlib
import secrets
import shutil
import urllib.parse

import sqlalchemy.orm
from flask import Flask
from flask import request

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.raster_map import GrayscaleImageTransform
from geo_activity_playground.core.raster_map import IdentityImageTransform
from geo_activity_playground.core.raster_map import PastelImageTransform
from geo_activity_playground.core.raster_map import TileGetter
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor
from geo_activity_playground.webui.activity.blueprint import make_activity_blueprint
from geo_activity_playground.webui.activity.controller import ActivityController
from geo_activity_playground.webui.auth_blueprint import make_auth_blueprint
from geo_activity_playground.webui.authenticator import Authenticator
from geo_activity_playground.webui.bubble_chart_blueprint import (
    make_bubble_chart_blueprint,
)
from geo_activity_playground.webui.calendar.blueprint import make_calendar_blueprint
from geo_activity_playground.webui.calendar.controller import CalendarController
from geo_activity_playground.webui.eddington_blueprint import make_eddington_blueprint
from geo_activity_playground.webui.equipment_blueprint import make_equipment_blueprint
from geo_activity_playground.webui.explorer.blueprint import make_explorer_blueprint
from geo_activity_playground.webui.explorer.controller import ExplorerController
from geo_activity_playground.webui.flasher import FlaskFlasher
from geo_activity_playground.webui.heatmap.blueprint import make_heatmap_blueprint
from geo_activity_playground.webui.search_blueprint import make_search_blueprint
from geo_activity_playground.webui.search_util import SearchQueryHistory
from geo_activity_playground.webui.settings.blueprint import make_settings_blueprint
from geo_activity_playground.webui.square_planner_blueprint import (
    make_square_planner_blueprint,
)
from geo_activity_playground.webui.summary_blueprint import make_summary_blueprint
from geo_activity_playground.webui.upload_blueprint import make_upload_blueprint
from geo_activity_playground.webui.views.entry_views import register_entry_views
from geo_activity_playground.webui.views.tile_views import register_tile_views


def get_secret_key():
    secret_file = pathlib.Path("Cache/flask-secret.json")
    if secret_file.exists():
        with open(secret_file) as f:
            secret = json.load(f)
    else:
        secret = secrets.token_hex()
        with open(secret_file, "w") as f:
            json.dump(secret, f)
    return secret


def web_ui_main(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config_accessor: ConfigAccessor,
    database: sqlalchemy.orm.Session,
    host: str,
    port: int,
) -> None:

    app = Flask(__name__)
    app.config["UPLOAD_FOLDER"] = "Activities"
    app.secret_key = get_secret_key()

    @app.template_filter()
    def dt(value: datetime.datetime):
        return value.strftime("%Y-%m-%d %H:%M")

    @app.template_filter()
    def td(v: datetime.timedelta):
        seconds = v.total_seconds()
        h = int(seconds // 3600)
        m = int(seconds // 60 % 60)
        s = int(seconds // 1 % 60)
        return f"{h}:{m:02d}:{s:02d}"

    authenticator = Authenticator(config_accessor())
    search_query_history = SearchQueryHistory(config_accessor, authenticator)
    config = config_accessor()
    activity_controller = ActivityController(repository, tile_visit_accessor, config)
    calendar_controller = CalendarController(repository)
    explorer_controller = ExplorerController(
        repository, tile_visit_accessor, config_accessor
    )
    tile_getter = TileGetter(config.map_tile_url)
    image_transforms = {
        "color": IdentityImageTransform(),
        "grayscale": GrayscaleImageTransform(),
        "pastel": PastelImageTransform(),
    }
    flasher = FlaskFlasher()

    register_entry_views(app, repository, config)
    register_tile_views(app, image_transforms, tile_getter)

    app.register_blueprint(make_auth_blueprint(authenticator), url_prefix="/auth")
    app.register_blueprint(
        make_activity_blueprint(activity_controller, repository, authenticator),
        url_prefix="/activity",
    )
    app.register_blueprint(
        make_calendar_blueprint(calendar_controller), url_prefix="/calendar"
    )
    app.register_blueprint(
        make_eddington_blueprint(repository, search_query_history),
        url_prefix="/eddington",
    )
    app.register_blueprint(
        make_equipment_blueprint(repository, config), url_prefix="/equipment"
    )
    app.register_blueprint(
        make_explorer_blueprint(explorer_controller, authenticator),
        url_prefix="/explorer",
    )
    app.register_blueprint(
        make_heatmap_blueprint(
            repository, tile_visit_accessor, config_accessor(), search_query_history
        ),
        url_prefix="/heatmap",
    )
    app.register_blueprint(
        make_settings_blueprint(config_accessor, authenticator, flasher),
        url_prefix="/settings",
    )
    app.register_blueprint(
        make_square_planner_blueprint(tile_visit_accessor),
        url_prefix="/square-planner",
    )
    app.register_blueprint(
        make_search_blueprint(
            repository, search_query_history, authenticator, config_accessor
        ),
        url_prefix="/search",
    )
    app.register_blueprint(
        make_summary_blueprint(repository, config, search_query_history),
        url_prefix="/summary",
    )
    app.register_blueprint(
        make_upload_blueprint(
            repository, tile_visit_accessor, config_accessor(), authenticator
        ),
        url_prefix="/upload",
    )

    bubble_chart_blueprint = make_bubble_chart_blueprint(repository)
    app.register_blueprint(bubble_chart_blueprint, url_prefix="/bubble-chart")

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
            "search_query_favorites": search_query_history.prepare_favorites(),
            "search_query_last": search_query_history.prepare_last(),
            "request_url": urllib.parse.quote_plus(request.url),
        }
        if len(repository):
            variables["equipments_avail"] = sorted(
                repository.meta["equipment"].unique()
            )
            variables["kinds_avail"] = sorted(repository.meta["kind"].unique())
        return variables

    app.run(host=host, port=port)


def _try_get_version():
    try:
        return importlib.metadata.version("geo-activity-playground")
    except importlib.metadata.PackageNotFoundError:
        pass
