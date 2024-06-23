from flask import Blueprint
from flask import render_template
from flask import Response

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .heatmap_controller import HeatmapController


def make_heatmap_blueprint(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> Blueprint:
    heatmap_controller = HeatmapController(repository, tile_visit_accessor)
    blueprint = Blueprint("heatmap", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        return render_template("heatmap/index.html.j2", **heatmap_controller.render())

    @blueprint.route("/tile/<z>/<x>/<y>.png")
    def tile(x: str, y: str, z: str):
        return Response(
            heatmap_controller.render_tile(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    @blueprint.route("/download/<north>/<east>/<south>/<west>")
    def download(north: str, east: str, south: str, west: str):
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

    return blueprint
