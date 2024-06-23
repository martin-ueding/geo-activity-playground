from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .controller import UploadController


def make_upload_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: dict,
) -> Blueprint:
    blueprint = Blueprint("upload", __name__, template_folder="templates")

    upload_controller = UploadController(repository, tile_visit_accessor, config)

    @blueprint.route("/")
    def index():
        return render_template(
            "upload/index.html.j2", **upload_controller.render_form()
        )

    @blueprint.route("/receive", methods=["POST"])
    def receive():
        return upload_controller.receive()

    return blueprint
