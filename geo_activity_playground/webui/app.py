import json
import pathlib
import secrets

from flask import Flask
from flask import redirect
from flask import render_template
from flask import request

from ..core.activities import ActivityRepository
from ..explorer.tile_visits import TileVisitAccessor
from .activity.blueprint import make_activity_blueprint
from .calendar.blueprint import make_calendar_blueprint
from .eddington.blueprint import make_eddington_blueprint
from .entry_controller import EntryController
from .equipment.blueprint import make_equipment_blueprint
from .explorer.blueprint import make_explorer_blueprint
from .heatmap.blueprint import make_heatmap_blueprint
from .search_controller import SearchController
from .square_planner.blueprint import make_square_planner_blueprint
from .strava_controller import StravaController
from .summary.blueprint import make_summary_blueprint
from .tile.blueprint import make_tile_blueprint
from .upload.blueprint import make_upload_blueprint
from geo_activity_playground.core.privacy_zones import PrivacyZone


def route_search(app: Flask, repository: ActivityRepository) -> None:
    search_controller = SearchController(repository)

    @app.route("/search", methods=["POST"])
    def search():
        form_input = request.form
        return render_template(
            "search.html.j2",
            **search_controller.render_search_results(form_input["name"])
        )


def route_start(app: Flask, repository: ActivityRepository) -> None:
    entry_controller = EntryController(repository)

    @app.route("/")
    def index():
        return render_template("home.html.j2", **entry_controller.render())


def route_strava(app: Flask, host: str, port: int) -> None:
    strava_controller = StravaController()

    @app.route("/strava/connect")
    def strava_connect():
        return render_template(
            "strava-connect.html.j2",
            host=host,
            port=port,
            **strava_controller.action_connect()
        )

    @app.route("/strava/authorize")
    def strava_authorize():
        client_id = request.form["client_id"]
        client_secret = request.form["client_secret"]
        return redirect(
            strava_controller.action_authorize(host, port, client_id, client_secret)
        )

    @app.route("/strava/callback")
    def strava_callback():
        code = request.args.get("code", type=str)
        return render_template(
            "strava-connect.html.j2",
            host=host,
            port=port,
            **strava_controller.action_connect()
        )


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


def webui_main(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: dict,
    host: str,
    port: int,
) -> None:
    app = Flask(__name__)

    route_search(app, repository)
    route_start(app, repository)
    route_strava(app, host, port)

    app.config["UPLOAD_FOLDER"] = "Activities"
    app.secret_key = get_secret_key()

    app.register_blueprint(
        make_activity_blueprint(
            repository,
            tile_visit_accessor,
            [
                PrivacyZone(points)
                for points in config.get("privacy_zones", {}).values()
            ],
        ),
        url_prefix="/activity",
    )
    app.register_blueprint(make_calendar_blueprint(repository), url_prefix="/calendar")
    app.register_blueprint(
        make_eddington_blueprint(repository), url_prefix="/eddington"
    )
    app.register_blueprint(
        make_equipment_blueprint(repository), url_prefix="/equipment"
    )
    app.register_blueprint(
        make_explorer_blueprint(repository, tile_visit_accessor), url_prefix="/explorer"
    )
    app.register_blueprint(
        make_heatmap_blueprint(repository, tile_visit_accessor), url_prefix="/heatmap"
    )
    app.register_blueprint(
        make_square_planner_blueprint(repository, tile_visit_accessor),
        url_prefix="/square-planner",
    )
    app.register_blueprint(
        make_summary_blueprint(repository),
        url_prefix="/summary",
    )
    app.register_blueprint(make_tile_blueprint(), url_prefix="/tile")
    app.register_blueprint(
        make_upload_blueprint(repository, tile_visit_accessor, config),
        url_prefix="/upload",
    )

    app.run(host=host, port=port)
