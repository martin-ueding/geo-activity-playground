import json
import os
import pathlib

import pytest

from geo_activity_playground.webui.app import create_app


@pytest.fixture
def password_client(tmp_path: pathlib.Path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "Cache").mkdir()
    (tmp_path / "Time Series").mkdir()
    (tmp_path / "Activities").mkdir()
    (tmp_path / "config.json").write_text(
        json.dumps({"upload_password": "test-password"}), encoding="utf-8"
    )
    try:
        app = create_app(
            database_uri="sqlite:///:memory:",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        app.config["TESTING"] = True
        yield app.test_client()
    finally:
        os.chdir(original_cwd)


def test_export_index_requires_authentication(password_client):
    response = password_client.get("/export/")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/?redirect=")


def test_export_download_requires_authentication(password_client):
    response = password_client.get(
        "/export/export?meta_format=json&activity_format=geojson"
    )
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/?redirect=")


def test_export_download_works_when_authenticated(password_client):
    with password_client.session_transaction() as session:
        session["is_authenticated"] = True

    response = password_client.get(
        "/export/export?meta_format=json&activity_format=geojson"
    )
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
