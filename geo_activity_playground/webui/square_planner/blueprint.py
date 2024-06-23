from flask import Blueprint
from flask import render_template
from flask import Response

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .controller import SquarePlannerController


def make_square_planner_blueprint(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> Blueprint:
    blueprint = Blueprint("square_planner", __name__, template_folder="templates")
    controller = SquarePlannerController(repository, tile_visit_accessor)

    @blueprint.route("/<zoom>/<x>/<y>/<size>")
    def index(zoom, x, y, size):
        return render_template(
            "square_planner/index.html.j2",
            **controller.action_planner(int(zoom), int(x), int(y), int(size))
        )

    @blueprint.route("/<zoom>/<x>/<y>/<size>/missing.<suffix>")
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

    return blueprint
