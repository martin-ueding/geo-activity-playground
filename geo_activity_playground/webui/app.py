import datetime
import importlib
import json
import pathlib
import secrets
import shutil
import urllib.parse

import sqlalchemy as sa
import sqlalchemy.orm
from flask import Flask
from flask import request

from ..core.activities import ActivityRepository
from ..core.config import ConfigAccessor
from ..core.raster_map import GrayscaleImageTransform
from ..core.raster_map import IdentityImageTransform
from ..core.raster_map import PastelImageTransform
from ..core.raster_map import TileGetter
from ..explorer.tile_visits import TileVisitAccessor
from .activity.blueprint import make_activity_blueprint
from .activity.controller import ActivityController
from .auth_blueprint import make_auth_blueprint
from .authenticator import Authenticator
from .calendar.blueprint import make_calendar_blueprint
from .calendar.controller import CalendarController
from .eddington_blueprint import make_eddington_blueprint
from .equipment_blueprint import make_equipment_blueprint
from .explorer.blueprint import make_explorer_blueprint
from .explorer.controller import ExplorerController
from .heatmap.blueprint import make_heatmap_blueprint
from .search_blueprint import make_search_blueprint
from .search_util import SearchQueryHistory
from .settings.blueprint import make_settings_blueprint
from .square_planner_blueprint import make_square_planner_blueprint
from .summary_blueprint import make_summary_blueprint
from .upload_blueprint import make_upload_blueprint
from .views.entry_views import EntryView
from .views.tile_views import TileView
from geo_activity_playground.core.datamodel import Base
from geo_activity_playground.webui.bubble_chart_blueprint import (
    make_bubble_chart_blueprint,
)
from geo_activity_playground.webui.flasher import FlaskFlasher
from geo_activity_playground.webui.interfaces import MyView
from geo_activity_playground.webui.views.settings_views import SettingsAdminPasswordView


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


def make_database_session() -> sqlalchemy.orm.Session:
    engine = sa.create_engine("sqlite:///database.sqlite", echo=False)
    Base.metadata.create_all(engine)
    return sqlalchemy.orm.Session(engine)


def web_ui_main(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config_accessor: ConfigAccessor,
    host: str,
    port: int,
) -> None:
    repository.reload()

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

    database = make_database_session()
    database.commit()
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
    views: list[MyView] = [
        EntryView(repository, config),
        SettingsAdminPasswordView(authenticator, config_accessor, flasher),
        TileView(image_transforms, tile_getter),
    ]

    for view in views:
        view.register(app)

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
        make_settings_blueprint(config_accessor, authenticator),
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
