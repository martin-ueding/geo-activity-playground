import json
import pathlib
import secrets

from flask import Flask
from flask import redirect
from flask import render_template
from flask import request
from flask import Response

from ..core.activities import ActivityRepository
from ..explorer.tile_visits import TileVisitAccessor
from .activity.blueprint import make_activity_blueprint
from .calendar.blueprint import make_calendar_blueprint
from .config_controller import ConfigController
from .eddington.blueprint import make_eddington_blueprint
from .entry_controller import EntryController
from .equipment.blueprint import make_equipment_blueprint
from .explorer_controller import ExplorerController
from .heatmap_controller import HeatmapController
from .locations_controller import LocationsController
from .search_controller import SearchController
from .square_planner_controller import SquarePlannerController
from .strava_controller import StravaController
from .summary_controller import SummaryController
from .tile.blueprint import make_tile_blueprint
from .upload.blueprint import make_upload_blueprint
from geo_activity_playground.webui.equipment.controller import EquipmentController


def route_config(app: Flask, repository: ActivityRepository) -> None:
    config_controller = ConfigController(repository)

    @app.route("/config")
    def config_index():
        return render_template("config.html.j2", **config_controller.action_index())

    @app.route("/config/save", methods=["POST"])
    def config_save():
        form_input = request.form
        return render_template(
            "config.html.j2", **config_controller.action_save(form_input)
        )


def route_explorer(
    app: Flask, repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> None:
    explorer_controller = ExplorerController(repository, tile_visit_accessor)

    @app.route("/explorer/<zoom>")
    def explorer(zoom: str):
        return render_template(
            "explorer.html.j2", **explorer_controller.render(int(zoom))
        )

    @app.route("/explorer/<zoom>/<north>/<east>/<south>/<west>/explored.<suffix>")
    def explorer_download(
        zoom: str, north: str, east: str, south: str, west: str, suffix: str
    ):
        mimetypes = {"geojson": "application/json", "gpx": "application/xml"}
        return Response(
            explorer_controller.export_explored_tiles(
                int(zoom),
                float(north),
                float(east),
                float(south),
                float(west),
                suffix,
            ),
            mimetype=mimetypes[suffix],
            headers={"Content-disposition": "attachment"},
        )

    @app.route("/explorer/<zoom>/<north>/<east>/<south>/<west>/missing.<suffix>")
    def explorer_missing(
        zoom: str, north: str, east: str, south: str, west: str, suffix: str
    ):
        mimetypes = {"geojson": "application/json", "gpx": "application/xml"}
        return Response(
            explorer_controller.export_missing_tiles(
                int(zoom),
                float(north),
                float(east),
                float(south),
                float(west),
                suffix,
            ),
            mimetype=mimetypes[suffix],
            headers={"Content-disposition": "attachment"},
        )


def route_heatmap(
    app: Flask, repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> None:
    heatmap_controller = HeatmapController(repository, tile_visit_accessor)

    @app.route("/heatmap")
    def heatmap():
        return render_template("heatmap.html.j2", **heatmap_controller.render())

    @app.route("/heatmap/tile/<z>/<x>/<y>.png")
    def heatmap_tile(x: str, y: str, z: str):
        return Response(
            heatmap_controller.render_tile(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    @app.route("/heatmap/download/<north>/<east>/<south>/<west>")
    def heatmap_download(north: str, east: str, south: str, west: str):
        return Response(
            heatmap_controller.download_heatmap(
                float(north),
                float(east),
                float(south),
                float(west),
            ),
            mimetype="image/png",
            headers={"Content-disposition": 'attachment; filename="heatmap.png"'},
        )


def route_locations(app: Flask, repository: ActivityRepository) -> None:
    controller = LocationsController(repository)

    @app.route("/locations")
    def locations_index():
        return render_template("locations.html.j2", **controller.render_index())


def route_search(app: Flask, repository: ActivityRepository) -> None:
    search_controller = SearchController(repository)

    @app.route("/search", methods=["POST"])
    def search():
        form_input = request.form
        return render_template(
            "search.html.j2",
            **search_controller.render_search_results(form_input["name"])
        )


def route_square_planner(
    app: Flask, repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> None:
    controller = SquarePlannerController(repository, tile_visit_accessor)

    @app.route("/square-planner/<zoom>/<x>/<y>/<size>")
    def square_planner_planner(zoom, x, y, size):
        return render_template(
            "square-planner.html.j2",
            **controller.action_planner(int(zoom), int(x), int(y), int(size))
        )

    @app.route("/square-planner/<zoom>/<x>/<y>/<size>/missing.<suffix>")
    def square_planner_missing(zoom, x, y, size, suffix: str):
        mimetypes = {"geojson": "application/json", "gpx": "application/xml"}
        return Response(
            controller.export_missing_tiles(
                int(zoom),
                int(x),
                int(y),
                int(size),
                suffix,
            ),
            mimetype=mimetypes[suffix],
            headers={"Content-disposition": "attachment"},
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


def route_summary(app: Flask, repository: ActivityRepository) -> None:
    summary_controller = SummaryController(repository)

    @app.route("/summary")
    def summary_statistics():
        return render_template("summary.html.j2", **summary_controller.render())


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

    route_config(app, repository)
    route_explorer(app, repository, tile_visit_accessor)
    route_heatmap(app, repository, tile_visit_accessor)
    route_locations(app, repository)
    route_search(app, repository)
    route_square_planner(app, repository, tile_visit_accessor)
    route_start(app, repository)
    route_strava(app, host, port)
    route_summary(app, repository)

    app.config["UPLOAD_FOLDER"] = "Activities"
    app.secret_key = get_secret_key()

    app.register_blueprint(make_activity_blueprint(repository), url_prefix="/activity")
    app.register_blueprint(make_calendar_blueprint(repository), url_prefix="/calendar")
    app.register_blueprint(
        make_eddington_blueprint(repository), url_prefix="/eddington"
    )
    app.register_blueprint(
        make_equipment_blueprint(repository), url_prefix="/equipment"
    )
    app.register_blueprint(make_tile_blueprint(), url_prefix="/tile")
    app.register_blueprint(
        make_upload_blueprint(repository, tile_visit_accessor, config),
        url_prefix="/upload",
    )

    app.run(host=host, port=port)
