from flask import Blueprint
from flask import render_template
from flask import Response

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .controller import ExplorerController


def make_explorer_blueprint(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> Blueprint:
    explorer_controller = ExplorerController(repository, tile_visit_accessor)
    blueprint = Blueprint("explorer", __name__, template_folder="templates")

    @blueprint.route("/<zoom>")
    def map(zoom: str):
        return render_template(
            "explorer/index.html.j2", **explorer_controller.render(int(zoom))
        )

    @blueprint.route("/<zoom>/<north>/<east>/<south>/<west>/explored.<suffix>")
    def download(zoom: str, north: str, east: str, south: str, west: str, suffix: str):
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

    @blueprint.route("/<zoom>/<north>/<east>/<south>/<west>/missing.<suffix>")
    def missing(zoom: str, north: str, east: str, south: str, west: str, suffix: str):
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

    return blueprint
