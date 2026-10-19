import pytest
from garminconnect import GarminConnectAuthenticationError

from geo_activity_playground.core.datamodel import DB
from geo_activity_playground.features.garmin import blueprint
from geo_activity_playground.features.garmin.model import get_garmin_auth

TOKENS = '{"di_token": "t"}'


class FakeClient:
    client = type("Inner", (), {"dumps": staticmethod(lambda: TOKENS)})()


def _tokens(app) -> str | None:
    with app.app_context():
        return get_garmin_auth().token_json


def test_page_renders_disconnected(client) -> None:
    response = client.get("/settings/garmin")
    assert response.status_code == 200
    assert b"Log in to Garmin" in response.data


def test_login_without_mfa_stores_tokens(
    client, app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        blueprint, "start_login", lambda _email, _password: (FakeClient(), False)
    )

    response = client.post(
        "/settings/garmin", data={"garmin_email": "a@b.c", "garmin_password": "pw"}
    )

    assert response.status_code == 302
    assert _tokens(app) == TOKENS


def test_login_with_mfa_needs_the_code(
    client, app, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeClient()
    monkeypatch.setattr(
        blueprint, "start_login", lambda _email, _password: (fake, True)
    )
    finished = []
    monkeypatch.setattr(
        blueprint, "finish_login", lambda c, code: finished.append((c, code))
    )

    client.post(
        "/settings/garmin", data={"garmin_email": "a@b.c", "garmin_password": "pw"}
    )
    assert _tokens(app) is None
    assert b"Finish login" in client.get("/settings/garmin?mfa=1").data

    client.post("/settings/garmin-mfa", data={"garmin_mfa_code": " 123456 "})

    assert finished == [(fake, "123456")]
    assert _tokens(app) == TOKENS


def test_mfa_without_pending_login_stores_nothing(client, app) -> None:
    response = client.post("/settings/garmin-mfa", data={"garmin_mfa_code": "123456"})
    assert response.status_code == 302
    assert _tokens(app) is None


def test_failed_login_stores_nothing(
    client, app, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(email, password):
        raise GarminConnectAuthenticationError("bad password")

    monkeypatch.setattr(blueprint, "start_login", fail)

    client.post(
        "/settings/garmin", data={"garmin_email": "a@b.c", "garmin_password": "pw"}
    )

    assert _tokens(app) is None


def test_disconnect_clears_tokens(client, app) -> None:
    with app.app_context():
        get_garmin_auth().token_json = "{}"
        DB.session.commit()

    client.post("/settings/garmin-disconnect")

    assert _tokens(app) is None
