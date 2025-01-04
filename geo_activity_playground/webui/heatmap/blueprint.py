import dateutil.parser
from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import Config
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor
from geo_activity_playground.webui.heatmap.heatmap_controller import HeatmapController


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
            **heatmap_controller.render(
                [int(k) for k in request.args.getlist("kind")],
                request.args.get(
                    "date-start", type=dateutil.parser.parse, default=None
                ),
                request.args.get("date-end", type=dateutil.parser.parse, default=None),
            )
        )

    @blueprint.route("/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(x: int, y: int, z: int):
        return Response(
            heatmap_controller.render_tile(
                x,
                y,
                z,
                [int(k) for k in request.args.getlist("kind")],
                request.args.get(
                    "date-start", type=dateutil.parser.parse, default=None
                ),
                request.args.get("date-end", type=dateutil.parser.parse, default=None),
            ),
            mimetype="image/png",
        )

    @blueprint.route(
        "/download/<float:north>/<float:east>/<float:south>/<float:west>/heatmap.png"
    )
    def download(north: float, east: float, south: float, west: float):
        return Response(
            heatmap_controller.download_heatmap(
                north,
                east,
                south,
                west,
                [int(k) for k in request.args.getlist("kind")],
                request.args.get(
                    "date-start", type=dateutil.parser.parse, default=None
                ),
                request.args.get("date-end", type=dateutil.parser.parse, default=None),
            ),
            mimetype="image/png",
            headers={"Content-disposition": 'attachment; filename="heatmap.png"'},
        )

    return blueprint
