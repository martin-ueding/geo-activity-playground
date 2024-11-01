import datetime
import importlib
import json
import pathlib
import secrets

from flask import Flask
from flask import render_template

from ..core.activities import ActivityRepository
from ..explorer.tile_visits import TileVisitAccessor
from .activity.blueprint import make_activity_blueprint
from .calendar.blueprint import make_calendar_blueprint
from .eddington.blueprint import make_eddington_blueprint
from .entry_controller import EntryController
from .equipment.blueprint import make_equipment_blueprint
from .explorer.blueprint import make_explorer_blueprint
from .heatmap.blueprint import make_heatmap_blueprint
from .search.blueprint import make_search_blueprint
from .square_planner.blueprint import make_square_planner_blueprint
from .summary.blueprint import make_summary_blueprint
from .tile.blueprint import make_tile_blueprint
from .upload.blueprint import make_upload_blueprint
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.webui.auth.blueprint import make_auth_blueprint
from geo_activity_playground.webui.authenticator import Authenticator
from geo_activity_playground.webui.settings.blueprint import make_settings_blueprint


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

    route_start(app, repository, config_accessor())

    app.register_blueprint(make_auth_blueprint(authenticator), url_prefix="/auth")

    app.register_blueprint(
        make_activity_blueprint(
            repository, tile_visit_accessor, config_accessor(), authenticator
        ),
        url_prefix="/activity",
    )
    app.register_blueprint(make_calendar_blueprint(repository), url_prefix="/calendar")
    app.register_blueprint(
        make_eddington_blueprint(repository), url_prefix="/eddington"
    )
    app.register_blueprint(
        make_equipment_blueprint(repository, config_accessor()), url_prefix="/equipment"
    )
    app.register_blueprint(
        make_explorer_blueprint(repository, tile_visit_accessor, config_accessor),
        url_prefix="/explorer",
    )
    app.register_blueprint(
        make_heatmap_blueprint(repository, tile_visit_accessor), url_prefix="/heatmap"
    )
    app.register_blueprint(
        make_settings_blueprint(config_accessor, authenticator),
        url_prefix="/settings",
    )
    app.register_blueprint(
        make_square_planner_blueprint(repository, tile_visit_accessor),
        url_prefix="/square-planner",
    )
    app.register_blueprint(
        make_search_blueprint(repository),
        url_prefix="/search",
    )
    app.register_blueprint(
        make_summary_blueprint(repository, config_accessor()),
        url_prefix="/summary",
    )
    app.register_blueprint(make_tile_blueprint(), url_prefix="/tile")
    app.register_blueprint(
        make_upload_blueprint(
            repository, tile_visit_accessor, config_accessor(), authenticator
        ),
        url_prefix="/upload",
    )

    @app.context_processor
    def inject_global_variables() -> dict:
        return {
            "version": _try_get_version(),
            "num_activities": len(repository),
        }

    app.run(host=host, port=port)


def _try_get_version():
    try:
        return importlib.metadata.version("geo-activity-playground")
    except importlib.metadata.PackageNotFoundError:
        pass
