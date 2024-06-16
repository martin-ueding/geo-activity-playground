import urllib

from flask import Flask
from flask import redirect
from flask import render_template
from flask import request
from flask import Response

from .locations_controller import LocationsController
from .search_controller import SearchController
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor
from geo_activity_playground.webui.activity_controller import ActivityController
from geo_activity_playground.webui.calendar_controller import CalendarController
from geo_activity_playground.webui.config_controller import ConfigController
from geo_activity_playground.webui.eddington_controller import EddingtonController
from geo_activity_playground.webui.entry_controller import EntryController
from geo_activity_playground.webui.equipment_controller import EquipmentController
from geo_activity_playground.webui.explorer_controller import ExplorerController
from geo_activity_playground.webui.heatmap_controller import HeatmapController
from geo_activity_playground.webui.search_controller import SearchController
from geo_activity_playground.webui.square_planner_controller import (
    SquarePlannerController,
)
from geo_activity_playground.webui.strava_controller import StravaController
from geo_activity_playground.webui.summary_controller import SummaryController
from geo_activity_playground.webui.tile_controller import (
    TileController,
)
from geo_activity_playground.webui.upload_controller import UploadController


def route_activity(app: Flask, repository: ActivityRepository) -> None:
    activity_controller = ActivityController(repository)

    @app.route("/activity/all")
    def activity_all():
        return render_template(
            "activity-lines.html.j2", **activity_controller.render_all()
        )

    @app.route("/activity/<id>")
    def activity(id: str):
        return render_template(
            "activity.html.j2", **activity_controller.render_activity(int(id))
        )

    @app.route("/activity/<id>/sharepic.png")
    def activity_sharepic(id: str):
        return Response(
            activity_controller.render_sharepic(int(id)),
            mimetype="image/png",
        )

    @app.route("/activity/day/<year>/<month>/<day>")
    def activity_day(year: str, month: str, day: str):
        return render_template(
            "activity-day.html.j2",
            **activity_controller.render_day(int(year), int(month), int(day))
        )

    @app.route("/activity/name/<name>")
    def activity_name(name: str):
        return render_template(
            "activity-name.html.j2",
            **activity_controller.render_name(urllib.parse.unquote(name))
        )


def route_calendar(app: Flask, repository: ActivityRepository) -> None:
    calendar_controller = CalendarController(repository)

    @app.route("/calendar")
    def calendar():
        return render_template(
            "calendar.html.j2", **calendar_controller.render_overview()
        )

    @app.route("/calendar/<year>/<month>")
    def calendar_month(year: str, month: str):
        return render_template(
            "calendar-month.html.j2",
            **calendar_controller.render_month(int(year), int(month))
        )


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


def route_eddington(app: Flask, repository: ActivityRepository) -> None:
    eddington_controller = EddingtonController(repository)

    @app.route("/eddington")
    def eddington():
        return render_template("eddington.html.j2", **eddington_controller.render())


def route_equipment(app: Flask, repository: ActivityRepository) -> None:
    equipment_controller = EquipmentController(repository)

    @app.route("/equipment")
    def equipment():
        return render_template("equipment.html.j2", **equipment_controller.render())


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
        return render_template("index.html.j2", **entry_controller.render())


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


def route_tiles(app: Flask, repository: ActivityRepository) -> None:
    tile_controller = TileController()

    @app.route("/tile/color/<z>/<x>/<y>.png")
    def tile_color(x: str, y: str, z: str):
        return Response(
            tile_controller.render_color(int(x), int(y), int(z)), mimetype="image/png"
        )

    @app.route("/tile/grayscale/<z>/<x>/<y>.png")
    def tile_grayscale(x: str, y: str, z: str):
        return Response(
            tile_controller.render_grayscale(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    @app.route("/tile/pastel/<z>/<x>/<y>.png")
    def tile_pastel(x: str, y: str, z: str):
        return Response(
            tile_controller.render_pastel(int(x), int(y), int(z)), mimetype="image/png"
        )


def route_upload(app: Flask):
    upload_controller = UploadController()

    @app.route("/upload")
    def form():
        return render_template("upload.html.j2", **upload_controller.render_form())

    @app.route("/upload/receive", methods=["POST"])
    def receive():
        return upload_controller.receive()


def webui_main(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    host: str,
    port: int,
) -> None:
    app = Flask(__name__)

    route_activity(app, repository)
    route_calendar(app, repository)
    route_config(app, repository)
    route_eddington(app, repository)
    route_equipment(app, repository)
    route_explorer(app, repository, tile_visit_accessor)
    route_heatmap(app, repository, tile_visit_accessor)
    route_locations(app, repository)
    route_search(app, repository)
    route_square_planner(app, repository, tile_visit_accessor)
    route_start(app, repository)
    route_strava(app, host, port)
    route_summary(app, repository)
    route_tiles(app, repository)
    route_upload(app)

    app.config["UPLOAD_FOLDER"] = "Activities"

    app.run(host=host, port=port)
