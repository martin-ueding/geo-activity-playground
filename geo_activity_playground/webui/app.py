import datetime
import importlib
import json
import pathlib
import secrets
import shutil
import urllib.parse

from flask import Flask
from flask import render_template

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.config import ConfigAccessor
from ..explorer.tile_visits import TileVisitAccessor
from .activity.blueprint import make_activity_blueprint
from .activity.controller import ActivityController
from .auth_blueprint import make_auth_blueprint
from .authenticator import Authenticator
from .calendar.blueprint import make_calendar_blueprint
from .calendar.controller import CalendarController
from .eddington_blueprint import make_eddington_blueprint
from .entry_controller import EntryController
from .equipment.blueprint import make_equipment_blueprint
from .equipment.controller import EquipmentController
from .explorer.blueprint import make_explorer_blueprint
from .explorer.controller import ExplorerController
from .heatmap.blueprint import make_heatmap_blueprint
from .search_blueprint import make_search_blueprint
from .settings.blueprint import make_settings_blueprint
from .square_planner_blueprint import make_square_planner_blueprint
from .summary_blueprint import make_summary_blueprint
from .tile_blueprint import make_tile_blueprint
from .upload_blueprint import make_upload_blueprint


def route_start(app: Flask, repository: ActivityRepository, config: Config) -> None:
    entry_controller = EntryController(repository, config)

    @app.route("/")
    def index():
        return render_template("home.html.j2", **entry_controller.render())


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

    authenticator = Authenticator(config_accessor())

    config = config_accessor()
    activity_controller = ActivityController(repository, tile_visit_accessor, config)
    calendar_controller = CalendarController(repository)
    equipment_controller = EquipmentController(repository, config)
    explorer_controller = ExplorerController(
        repository, tile_visit_accessor, config_accessor
    )

    route_start(app, repository, config_accessor())

    app.register_blueprint(make_auth_blueprint(authenticator), url_prefix="/auth")
    app.register_blueprint(
        make_activity_blueprint(activity_controller, repository, authenticator),
        url_prefix="/activity",
    )
    app.register_blueprint(
        make_calendar_blueprint(calendar_controller), url_prefix="/calendar"
    )
    app.register_blueprint(
        make_eddington_blueprint(repository), url_prefix="/eddington"
    )
    app.register_blueprint(
        make_equipment_blueprint(equipment_controller), url_prefix="/equipment"
    )
    app.register_blueprint(
        make_explorer_blueprint(explorer_controller), url_prefix="/explorer"
    )
    app.register_blueprint(
        make_heatmap_blueprint(repository, tile_visit_accessor, config_accessor()),
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
        make_search_blueprint(repository),
        url_prefix="/search",
    )
    app.register_blueprint(
        make_summary_blueprint(repository, config), url_prefix="/summary"
    )

    app.register_blueprint(make_tile_blueprint(config), url_prefix="/tile")
    app.register_blueprint(
        make_upload_blueprint(
            repository, tile_visit_accessor, config_accessor(), authenticator
        ),
        url_prefix="/upload",
    )

    base_dir = pathlib.Path("Open Street Map Tiles")
    dir_for_source = base_dir / urllib.parse.quote_plus(config_accessor().map_tile_url)
    if base_dir.exists() and not dir_for_source.exists():
        subdirs = base_dir.glob("*")
        dir_for_source.mkdir()
        for subdir in subdirs:
            shutil.move(subdir, dir_for_source)

    @app.context_processor
    def inject_global_variables() -> dict:
        return {
            "version": _try_get_version(),
            "num_activities": len(repository),
            "map_tile_attribution": config_accessor().map_tile_attribution,
        }

    app.run(host=host, port=port)


def _try_get_version():
    try:
        return importlib.metadata.version("geo-activity-playground")
    except importlib.metadata.PackageNotFoundError:
        pass
