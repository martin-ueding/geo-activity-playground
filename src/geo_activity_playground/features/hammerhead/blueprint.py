import secrets
import urllib.parse

import sqlalchemy
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...core.datamodel import DB
from ...webui.authenticator import Authenticator, needs_authentication
from .importer import (
    HAMMERHEAD_OAUTH_SCOPE,
    HammerheadAuthError,
    exchange_code_for_token,
)
from .model import HammerheadAuth, get_hammerhead_auth


class HammerheadLoginHelper:
    def render_hammerhead(self) -> dict:
        auth = DB.session.scalar(sqlalchemy.select(HammerheadAuth).limit(1))
        return {
            "hammerhead_client_id": auth.client_id if auth else None,
            "hammerhead_client_secret": auth.client_secret if auth else None,
            "hammerhead_client_code": auth.client_code if auth else None,
        }

    def save_hammerhead(self, client_id: str, client_secret: str) -> str:
        auth = get_hammerhead_auth()
        auth.client_id = client_id
        auth.client_secret = client_secret
        auth.redirect_uri = url_for(".hammerhead_callback", _external=True)
        DB.session.commit()

        state = secrets.token_urlsafe(32)
        session["hammerhead_oauth_state"] = state

        payload = {
            "client_id": client_id,
            "redirect_uri": auth.redirect_uri,
            "response_type": "code",
            "scope": HAMMERHEAD_OAUTH_SCOPE,
            "state": state,
        }

        arg_string = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in payload.items()
        )
        return f"https://api.hammerhead.io/v1/auth/oauth/authorize?{arg_string}"

    def save_hammerhead_code(self, code: str) -> None:
        auth = get_hammerhead_auth()
        auth.client_code = code
        DB.session.commit()
        try:
            exchange_code_for_token(auth)
        except HammerheadAuthError as e:
            flash(
                _("Could not connect to Hammerhead API: %(error)s", error=str(e)),
                category="danger",
            )
            return
        flash(_("Connected to Hammerhead API"), category="success")

    def disconnect_hammerhead(self) -> None:
        auth = get_hammerhead_auth()
        auth.client_code = None
        auth.access_token = None
        auth.refresh_token = None
        auth.expires_at = None
        DB.session.commit()
        flash(_("Disconnected from Hammerhead API"), category="success")


def register_hammerhead_settings(
    blueprint: Blueprint, authenticator: Authenticator
) -> None:
    """Register the Hammerhead API connect/callback/disconnect routes onto the settings blueprint."""
    hammerhead_login_helper = HammerheadLoginHelper()

    @blueprint.route("/hammerhead", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def hammerhead():
        if request.method == "POST":
            client_id = request.form["hammerhead_client_id"].strip()
            client_secret = request.form["hammerhead_client_secret"].strip()
            url = hammerhead_login_helper.save_hammerhead(client_id, client_secret)
            return redirect(url)
        return render_template(
            "settings/hammerhead.html.j2",
            **hammerhead_login_helper.render_hammerhead(),
        )

    @blueprint.route("/hammerhead-callback")
    @needs_authentication(authenticator)
    def hammerhead_callback():
        code = request.args.get("code", type=str)
        assert code
        state = request.args.get("state", type=str)
        expected_state = session.pop("hammerhead_oauth_state", None)
        if not expected_state or state != expected_state:
            flash(
                _("Hammerhead authorization failed: invalid or missing state."),
                category="danger",
            )
            return redirect(url_for(".hammerhead"))
        hammerhead_login_helper.save_hammerhead_code(code)
        return redirect(url_for(".hammerhead"))

    @blueprint.route("/hammerhead-disconnect", methods=["POST"])
    @needs_authentication(authenticator)
    def hammerhead_disconnect():
        hammerhead_login_helper.disconnect_hammerhead()
        return redirect(url_for(".hammerhead"))
