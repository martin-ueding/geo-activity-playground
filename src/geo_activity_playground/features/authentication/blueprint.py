from flask import Blueprint, Response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from ...core.config import ConfigAccessor
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes


def make_authentication_blueprint(
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
    flasher: Flasher,
) -> Blueprint:
    blueprint = Blueprint("authentication", __name__, template_folder="templates")

    @blueprint.route("/login", methods=["GET", "POST"])
    def login() -> ResponseReturnValue:
        if request.method == "POST":
            authenticator.authenticate(request.form["password"])
            if redirect_to := request.form["redirect"]:
                return redirect(redirect_to)
        return render_template(
            "authentication/login.html.j2",
            is_authenticated=authenticator.is_authenticated(),
            redirect=request.args.get("redirect", ""),
        )

    @blueprint.route("/logout")
    def logout() -> ResponseReturnValue:
        authenticator.logout()
        return redirect(url_for(".login"))

    @blueprint.route("/change-password", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def change_password() -> Response:
        if request.method == "POST":
            config_accessor.activity_import().upload_password = request.form["password"]
            config_accessor.save()
            flasher.flash_message("Updated admin password.", FlashTypes.SUCCESS)
        return Response(
            render_template(
                "authentication/change-password.html.j2",
                password=config_accessor.activity_import().upload_password,
            )
        )

    return blueprint
