from flask import Flask
from flask import render_template
from flask import request
from flask import Response

from .search_controller import SearchController
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.webui.activity_controller import ActivityController
from geo_activity_playground.webui.calendar_controller import CalendarController
from geo_activity_playground.webui.eddington_controller import EddingtonController
from geo_activity_playground.webui.entry_controller import EntryController
from geo_activity_playground.webui.equipment_controller import EquipmentController
from geo_activity_playground.webui.explorer_controller import ExplorerController
from geo_activity_playground.webui.heatmap_controller import HeatmapController
from geo_activity_playground.webui.summary_controller import SummaryController
from geo_activity_playground.webui.tile_controller import (
    TileController,
)


def route_activity(app: Flask, repository: ActivityRepository) -> None:
    activity_controller = ActivityController(repository)

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


def route_calendar(app: Flask, repository: ActivityRepository) -> None:
    calendar_controller = CalendarController(repository)

    @app.route("/calendar")
    def calendar():
        return render_template(
            "calendar.html.j2", **calendar_controller.render_overview()
        )

    @app.route("/calendar/<year>/<month>")
    def calendar_year_month(year: str, month: str):
        return render_template(
            "calendar-month.html.j2",
            **calendar_controller.render_month(int(year), int(month))
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


def route_explorer(app: Flask, repository: ActivityRepository) -> None:
    explorer_controller = ExplorerController(repository)

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


def route_heatmap(app: Flask, repository: ActivityRepository) -> None:
    heatmap_controller = HeatmapController(repository)

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
        return render_template("index.html.j2", **entry_controller.render())


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
            tile_controller.render_color(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    @app.route("/tile/grayscale/<z>/<x>/<y>.png")
    def tile_grayscale(x: str, y: str, z: str):
        return Response(
            tile_controller.render_grayscale(int(x), int(y), int(z)),
            mimetype="image/png",
        )


def webui_main(repository: ActivityRepository, host: str, port: int) -> None:
    app = Flask(__name__)

    route_activity(app, repository)
    route_calendar(app, repository)
    route_eddington(app, repository)
    route_equipment(app, repository)
    route_explorer(app, repository)
    route_heatmap(app, repository)
    route_search(app, repository)
    route_start(app, repository)
    route_summary(app, repository)
    route_tiles(app, repository)

    app.run(host=host, port=port)
