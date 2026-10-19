"""Shared fixtures for all tests."""

import os
import pathlib
import shutil

import jinja2
import pytest
from flask import Flask

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB
from geo_activity_playground.core.scan import remote_families, scan_for_activities
from geo_activity_playground.webui.app import create_app

METADATA_EXTRACTION_REGEXES = [
    r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
    r"(?P<kind>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
]


@pytest.fixture(autouse=True)
def _clear_process_caches():
    """Drop caches that live in module state, so tests do not see each other.

    Each test gets a fresh in-memory database whose ids restart from one, which
    makes cache keys from different tests collide.
    """
    from geo_activity_playground.features.explorer import filtered
    from geo_activity_playground.features.explorer.tile_rendering import (
        clear_highlight_caches,
    )

    filtered._process_cache.clear()
    clear_highlight_caches()
    yield
    filtered._process_cache.clear()
    clear_highlight_caches()


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
    for name in PLAYGROUND_DIRS:
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


PLAYGROUND_DIRS = ["Cache", "Time Series", "Activities", "Photos"]

SEEDED_DATABASE = "seeded.sqlite"


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A playground with the Zeeland test corpus imported, built once.

    Running the import costs several seconds, which dominated the suite when
    every test that needs activities paid it again. The result is a directory
    that ``seeded_app`` copies, so each test still gets untouched state.
    """
    template = tmp_path_factory.mktemp("seeded-template")
    testdata_dir = pathlib.Path(__file__).parent.parent / "testdata"
    previous_dir = pathlib.Path.cwd()
    os.chdir(template)
    try:
        for name in PLAYGROUND_DIRS:
            (template / name).mkdir()
        shutil.copytree(
            testdata_dir / "Zeeland" / "Activities",
            template / "Activities",
            dirs_exist_ok=True,
        )
        app = create_app(
            database_uri=f"sqlite:///{template / SEEDED_DATABASE}",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        with app.app_context():
            config_accessor = ConfigAccessor()
            config_accessor.activity_import().metadata_extraction_regexes = (
                METADATA_EXTRACTION_REGEXES
            )
            config_accessor.save()
            scan_for_activities(config_accessor, skip=remote_families())
            # Flush the file, so that copies of it are complete.
            DB.engine.dispose()
    finally:
        os.chdir(previous_dir)
    return template


@pytest.fixture
def seeded_app(playground: pathlib.Path, seeded_template: pathlib.Path):
    """An app whose database is filled by importing the Zeeland test corpus.

    This exercises the real import pipeline, so the database contains
    activities, time series, kinds, equipments, tile visits and clusters. The
    import itself runs once per session in ``seeded_template``; this copy of it
    is private to the test and may be modified freely.
    """
    for name in PLAYGROUND_DIRS:
        shutil.copytree(seeded_template / name, playground / name, dirs_exist_ok=True)
    database = playground / SEEDED_DATABASE
    shutil.copy(seeded_template / SEEDED_DATABASE, database)

    app = create_app(
        database_uri=f"sqlite:///{database}",
        secret_key="test-secret-key",
        run_migrations=False,
    )
    app.config["TESTING"] = True
    app.jinja_env.undefined = jinja2.StrictUndefined
    return app


@pytest.fixture
def seeded_client(seeded_app: Flask):
    return seeded_app.test_client()
