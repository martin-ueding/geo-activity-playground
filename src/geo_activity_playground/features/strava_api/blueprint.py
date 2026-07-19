import urllib.parse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...core.paths import strava_api_dir
from ...webui.authenticator import Authenticator, needs_authentication


class StravaLoginHelper:
    def __init__(self, config_accessor: ConfigAccessor) -> None:
        self._config_accessor = config_accessor

    def render_strava(self) -> dict:
        return {
            "strava_client_id": self._config_accessor.strava().strava_client_id,
            "strava_client_secret": self._config_accessor.strava().strava_client_secret,
            "strava_client_code": self._config_accessor.strava().strava_client_code,
        }

    def save_strava(self, client_id: str, client_secret: str) -> str:
        self._strava_client_id = client_id
        self._strava_client_secret = client_secret

        payload = {
            "client_id": client_id,
            "redirect_uri": url_for(".strava_callback", _external=True),
            "response_type": "code",
            "scope": "activity:read_all",
        }

        arg_string = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in payload.items()
        )
        return f"https://www.strava.com/oauth/authorize?{arg_string}"

    def save_strava_code(self, code: str) -> None:
        self._config_accessor.strava().strava_client_id = int(self._strava_client_id)
        self._config_accessor.strava().strava_client_secret = self._strava_client_secret
        self._config_accessor.strava().strava_client_code = code
        self._config_accessor.save()
        flash("Connected to Strava API", category="success")

    def disconnect_strava(self) -> None:
        self._config_accessor.strava().strava_client_code = None
        self._config_accessor.save()
        (strava_api_dir() / "strava_tokens.json").unlink(missing_ok=True)
        flash(_("Disconnected from Strava API"), category="success")


def register_strava_api_settings(
    blueprint: Blueprint, authenticator: Authenticator, config_accessor: ConfigAccessor
) -> None:
    """Register the Strava API connect/callback/disconnect routes onto the settings blueprint."""
    strava_login_helper = StravaLoginHelper(config_accessor)

    @blueprint.route("/strava", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def strava():
        if request.method == "POST":
            strava_client_id = request.form["strava_client_id"]
            strava_client_secret = request.form["strava_client_secret"]
            url = strava_login_helper.save_strava(
                strava_client_id, strava_client_secret
            )
            return redirect(url)
        return render_template(
            "settings/strava.html.j2", **strava_login_helper.render_strava()
        )

    @blueprint.route("/strava-callback")
    @needs_authentication(authenticator)
    def strava_callback():
        code = request.args.get("code", type=str)
        assert code
        strava_login_helper.save_strava_code(code)
        return redirect(url_for(".strava"))

    @blueprint.route("/strava-disconnect", methods=["POST"])
    @needs_authentication(authenticator)
    def strava_disconnect():
        strava_login_helper.disconnect_strava()
        return redirect(url_for(".strava"))
