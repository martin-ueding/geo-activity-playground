import dateutil.parser
from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import Config
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor
from geo_activity_playground.webui.heatmap.heatmap_controller import HeatmapController
from geo_activity_playground.webui.search_util import search_query_from_form


def make_heatmap_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
) -> Blueprint:
    heatmap_controller = HeatmapController(repository, tile_visit_accessor, config)
    blueprint = Blueprint("heatmap", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        return render_template(
            "heatmap/index.html.j2", **heatmap_controller.render(query)
        )

    @blueprint.route("/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(x: int, y: int, z: int):
        query = search_query_from_form(request.args)
        return Response(
            heatmap_controller.render_tile(x, y, z, query),
            mimetype="image/png",
        )

    @blueprint.route(
        "/download/<float:north>/<float:east>/<float:south>/<float:west>/heatmap.png"
    )
    def download(north: float, east: float, south: float, west: float):
        query = search_query_from_form(request.args)
        return Response(
            heatmap_controller.download_heatmap(north, east, south, west, query),
            mimetype="image/png",
            headers={"Content-disposition": 'attachment; filename="heatmap.png"'},
        )

    return blueprint
