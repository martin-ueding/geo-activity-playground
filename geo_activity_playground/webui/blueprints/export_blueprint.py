from datetime import date

from flask import Blueprint, Response, render_template, request

from ...core.export import export_all
from ..authenticator import Authenticator, needs_authentication


def make_export_blueprint(authenticator: Authenticator) -> Blueprint:
    blueprint = Blueprint("export", __name__, template_folder="templates")

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index() -> str:
        return render_template("export/index.html.j2")

    @blueprint.route("/export")
    @needs_authentication(authenticator)
    def export() -> Response:
        meta_format = request.args["meta_format"]
        activity_format = request.args["activity_format"]
        return Response(
            bytes(export_all(meta_format, activity_format)),
            mimetype="application/zip",
            headers={
                "Content-disposition": f'attachment; filename="GAP-export-{date.today().strftime("%Y-%m-%d")}.zip"'
            },
        )

    return blueprint
