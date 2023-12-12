from flask import Flask
from flask import render_template
from flask import Response

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.webui.activity_controller import ActivityController
from geo_activity_playground.webui.calendar_controller import CalendarController
from geo_activity_playground.webui.eddington_controller import EddingtonController
from geo_activity_playground.webui.entry_controller import EntryController
from geo_activity_playground.webui.equipment_controller import EquipmentController
from geo_activity_playground.webui.explorer_controller import ExplorerController
from geo_activity_playground.webui.grayscale_tile_controller import (
    GrayscaleTileController,
)
from geo_activity_playground.webui.heatmap_controller import HeatmapController
from geo_activity_playground.webui.summary_controller import SummaryController


def webui_main(repository: ActivityRepository, host: str, port: int) -> None:
    app = Flask(__name__)

    entry_controller = EntryController(repository)
    calendar_controller = CalendarController(repository)
    eddington_controller = EddingtonController(repository)
    activity_controller = ActivityController(repository)
    explorer_controller = ExplorerController(repository)
    equipment_controller = EquipmentController(repository)
    heatmap_controller = HeatmapController(repository)
    grayscale_tile_controller = GrayscaleTileController()
    summary_controller = SummaryController(repository)

    @app.route("/")
    def index():
        return render_template("index.html.j2", **entry_controller.render())

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

    @app.route("/summary-statistics")
    def summary_statistics():
        return render_template(
            "summary-statistics.html.j2", **summary_controller.render()
        )

    @app.route("/eddington")
    def eddington():
        return render_template("eddington.html.j2", **eddington_controller.render())

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

    @app.route("/equipment")
    def equipment():
        return render_template("equipment.html.j2", **equipment_controller.render())

    @app.route("/heatmap")
    def heatmap():
        return render_template("heatmap.html.j2", **heatmap_controller.render())

    @app.route("/heatmap/tile/<z>/<x>/<y>.png")
    def heatmap_tile(x: str, y: str, z: str):
        return Response(
            heatmap_controller.render_tile(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    @app.route("/grayscale-tile/<z>/<x>/<y>.png")
    def grayscale_tile(x: str, y: str, z: str):
        return Response(
            grayscale_tile_controller.render_tile(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    app.run(host=host, port=port)
