from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request

from .controller import StravaController


def make_strava_blueprint(host: str, port: int) -> Blueprint:
    strava_controller = StravaController(host, port)
    blueprint = Blueprint("strava", __name__, template_folder="templates")

    @blueprint.route("/connect")
    def connect():
        return render_template("strava/connect.html.j2", **strava_controller.connect())

    @blueprint.route("/authorize")
    def strava_authorize():
        client_id = request.form["client_id"]
        client_secret = request.form["client_secret"]
        return redirect(strava_controller.authorize(client_id, client_secret))

    @blueprint.route("/callback")
    def strava_callback():
        code = request.args.get("code", type=str)
        return render_template("strava/connect.html.j2", **strava_controller.connect())

    return blueprint
