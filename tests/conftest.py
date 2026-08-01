"""Shared fixtures for all tests."""

import pathlib
import shutil

import jinja2
import pytest
from flask import Flask

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.scan import scan_for_activities
from geo_activity_playground.webui.app import create_app

METADATA_EXTRACTION_REGEXES = [
    r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
    r"(?P<kind>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
]


@pytest.fixture
def testdata_dir() -> pathlib.Path:
    return pathlib.Path(__file__).parent.parent / "testdata"


@pytest.fixture
def playground(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """A playground directory as the working directory.

    The code addresses its state through relative paths, so tests have to run
    inside a directory of their own.
    """
    monkeypatch.chdir(tmp_path)
    for name in ["Cache", "Time Series", "Activities", "Photos"]:
        (tmp_path / name).mkdir()
    return tmp_path


@pytest.fixture
def app(playground: pathlib.Path):
    """A Flask app on an in-memory database, built by the production factory.

    The schema comes from ``DB.create_all()`` instead of the migrations, which
    is much faster; ``test_schema_drift`` asserts that both agree.
    """
    app = create_app(
        database_uri="sqlite:///:memory:",
        secret_key="test-secret-key",
        run_migrations=False,
    )
    app.config["TESTING"] = True
    app.jinja_env.undefined = jinja2.StrictUndefined
    return app


@pytest.fixture
def app_context(app: Flask):
    with app.app_context():
        yield


@pytest.fixture
def client(app: Flask):
    return app.test_client()


@pytest.fixture
def seeded_app(app: Flask, testdata_dir: pathlib.Path):
    """An app whose database is filled by importing the Zeeland test corpus.

    This exercises the real import pipeline, so the database contains
    activities, time series, kinds, equipments, tile visits and clusters.
    """
    shutil.copytree(
        testdata_dir / "Zeeland" / "Activities",
        pathlib.Path("Activities"),
        dirs_exist_ok=True,
    )
    with app.app_context():
        config_accessor = ConfigAccessor()
        config_accessor.activity_import().metadata_extraction_regexes = (
            METADATA_EXTRACTION_REGEXES
        )
        config_accessor.save()
        scan_for_activities(
            ActivityRepository(),
            config_accessor,
            skip_strava=True,
            skip_hammerhead=True,
        )
    return app


@pytest.fixture
def seeded_client(seeded_app: Flask):
    return seeded_app.test_client()
