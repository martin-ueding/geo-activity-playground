import secrets
import threading
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from ...core.datamodel import DB
from ...webui.authenticator import Authenticator, needs_authentication
from .importer import finish_login, start_login, store_tokens
from .model import get_garmin_auth

PENDING_LOGIN_SECONDS = 600

# The client that waits for the MFA code holds the state of the login, so it has to
# stay in memory between the two requests. That works only if both requests are
# handled by the same worker process; otherwise the user starts over.
_pending_logins: dict[str, tuple[float, Garmin]] = {}
_pending_lock = threading.Lock()


def _remember_pending(client: Garmin) -> None:
    key = secrets.token_urlsafe(16)
    now = time.monotonic()
    with _pending_lock:
        for stale in [
            k
            for k, (t, _) in _pending_logins.items()
            if now - t > PENDING_LOGIN_SECONDS
        ]:
            del _pending_logins[stale]
        _pending_logins[key] = (now, client)
    session["garmin_pending_login"] = key


def _take_pending() -> Garmin | None:
    key = session.pop("garmin_pending_login", None)
    with _pending_lock:
        entry = _pending_logins.pop(key, None) if key else None
    if entry is None or time.monotonic() - entry[0] > PENDING_LOGIN_SECONDS:
        return None
    return entry[1]


def _login_error_message(error: Exception) -> str:
    if isinstance(error, GarminConnectTooManyRequestsError):
        return _(
            "Garmin is limiting login attempts. Please wait before you try again, as trying again right away can prolong the block."
        )
    return _("Could not log in to Garmin: %(error)s", error=str(error))


def register_garmin_settings(
    blueprint: Blueprint, authenticator: Authenticator
) -> None:
    """Register the Garmin login and disconnect routes onto the settings blueprint."""

    @blueprint.route("/garmin", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def garmin():
        if request.method == "POST":
            email = request.form["garmin_email"].strip()
            password = request.form["garmin_password"]
            try:
                client, needs_mfa = start_login(email, password)
            except (
                GarminConnectAuthenticationError,
                GarminConnectConnectionError,
                GarminConnectTooManyRequestsError,
            ) as e:
                flash(_login_error_message(e), category="danger")
                return redirect(url_for(".garmin"))
            if needs_mfa:
                _remember_pending(client)
                return redirect(url_for(".garmin", mfa=1))
            store_tokens(get_garmin_auth(), client)
            flash(_("Connected to Garmin"), category="success")
            return redirect(url_for(".garmin"))
        return render_template(
            "settings/garmin.html.j2",
            garmin_connected=bool(get_garmin_auth().token_json),
            mfa_pending=bool(request.args.get("mfa")),
        )

    @blueprint.route("/garmin-mfa", methods=["POST"])
    @needs_authentication(authenticator)
    def garmin_mfa():
        client = _take_pending()
        if client is None:
            flash(
                _(
                    "The login has expired or was started on another server process. Please log in again, or use the command line: geo-activity-playground garmin-login"
                ),
                category="danger",
            )
            return redirect(url_for(".garmin"))
        try:
            finish_login(client, request.form["garmin_mfa_code"].strip())
        except (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
        ) as e:
            flash(_login_error_message(e), category="danger")
            return redirect(url_for(".garmin"))
        store_tokens(get_garmin_auth(), client)
        flash(_("Connected to Garmin"), category="success")
        return redirect(url_for(".garmin"))

    @blueprint.route("/garmin-disconnect", methods=["POST"])
    @needs_authentication(authenticator)
    def garmin_disconnect():
        get_garmin_auth().token_json = None
        DB.session.commit()
        flash(_("Disconnected from Garmin"), category="success")
        return redirect(url_for(".garmin"))
