from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response
from flask.typing import ResponseReturnValue

from ...core.export import export_all
from ..authenticator import Authenticator
from ..authenticator import needs_authentication


def make_export_blueprint(authenticator: Authenticator) -> Blueprint:
    blueprint = Blueprint("export", __name__, template_folder="templates")

    @needs_authentication(authenticator)
    @blueprint.route("/")
    def index() -> str:
        return render_template("export/index.html.j2")

    @needs_authentication(authenticator)
    @blueprint.route("/export")
    def export() -> Response:
        meta_format = request.args["meta_format"]
        activity_format = request.args["activity_format"]
        return Response(
            bytes(export_all(meta_format, activity_format)),
            mimetype="application/zip",
            headers={"Content-disposition": 'attachment; filename="export.zip"'},
        )

    return blueprint
