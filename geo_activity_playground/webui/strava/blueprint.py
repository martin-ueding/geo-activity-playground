from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request

from .controller import StravaController


def make_strava_blueprint(host: str, port: int) -> Blueprint:
    strava_controller = StravaController(host, port)
    blueprint = Blueprint("strava", __name__, template_folder="templates")

    @blueprint.route("/setup")
    def setup():
        return render_template(
            "strava/client-id.html.j2", **strava_controller.set_client_id()
        )

    @blueprint.route("/post-client-id", methods=["POST"])
    def post_client_id():
        client_id = request.form["client_id"]
        client_secret = request.form["client_secret"]
        url = strava_controller.save_client_id(client_id, client_secret)
        return redirect(url)

    @blueprint.route("/callback")
    def strava_callback():
        code = request.args.get("code", type=str)
        return render_template(
            "strava/connected.html.j2", **strava_controller.save_code(code)
        )

    return blueprint
