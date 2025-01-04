from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .heatmap_controller import HeatmapController
from geo_activity_playground.core.config import Config


def make_heatmap_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
) -> Blueprint:
    heatmap_controller = HeatmapController(repository, tile_visit_accessor, config)
    blueprint = Blueprint("heatmap", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        return render_template(
            "heatmap/index.html.j2",
            **heatmap_controller.render(request.args.getlist("kind"))
        )

    @blueprint.route("/tile/<int:z>/<int:x>/<int:y>/<kinds>.png")
    def tile(x: int, y: int, z: int, kinds: str):
        return Response(
            heatmap_controller.render_tile(x, y, z, kinds.split(";")),
            mimetype="image/png",
        )

    @blueprint.route(
        "/download/<float:north>/<float:east>/<float:south>/<float:west>/<kinds>"
    )
    def download(north: float, east: float, south: float, west: float, kinds: str):
        return Response(
            heatmap_controller.download_heatmap(
                north, east, south, west, kinds.split(";")
            ),
            mimetype="image/png",
            headers={"Content-disposition": 'attachment; filename="heatmap.png"'},
        )

    return blueprint
