from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask.typing import ResponseReturnValue

from ..authenticator import Authenticator


def make_auth_blueprint(authenticator: Authenticator) -> Blueprint:
    blueprint = Blueprint("auth", __name__, template_folder="templates")

    @blueprint.route("/", methods=["GET", "POST"])
    def index() -> ResponseReturnValue:
        if request.method == "POST":
            authenticator.authenticate(request.form["password"])
            if redirect_to := request.form["redirect"]:
                return redirect(redirect_to)
        return render_template(
            "auth/index.html.j2",
            is_authenticated=authenticator.is_authenticated(),
            redirect=request.args.get("redirect", ""),
        )

    @blueprint.route("/logout")
    def logout() -> ResponseReturnValue:
        authenticator.logout()
        return redirect(url_for(".index"))

    return blueprint
