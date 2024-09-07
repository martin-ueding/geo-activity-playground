from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .controller import UploadController
from geo_activity_playground.core.config import Config
from geo_activity_playground.webui.authenticator import Authenticator
from geo_activity_playground.webui.authenticator import needs_authentication


def make_upload_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("upload", __name__, template_folder="templates")

    upload_controller = UploadController(repository, tile_visit_accessor, config)

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        return render_template(
            "upload/index.html.j2", **upload_controller.render_form()
        )

    @blueprint.route("/receive", methods=["POST"])
    @needs_authentication(authenticator)
    def receive():
        return upload_controller.receive()

    @blueprint.route("/refresh")
    @needs_authentication(authenticator)
    def reload():
        return render_template("upload/reload.html.j2")

    @blueprint.route("/execute-reload")
    @needs_authentication(authenticator)
    def execute_reload():
        return upload_controller.execute_reload()

    return blueprint
