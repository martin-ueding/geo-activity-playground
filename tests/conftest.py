"""
Test fixtures for Flask web UI testing.
"""

import os
import pathlib

import pytest
from flask import Flask

from geo_activity_playground.webui.app import create_app


@pytest.fixture
def app(tmp_path: pathlib.Path):
    """
    Create a Flask app with an in-memory SQLite database for testing.

    Uses the same create_app factory as production, but with:
    - In-memory SQLite database
    - DB.create_all() instead of Alembic migrations (faster)
    - Temporary directory for file-based state
    """
    # Save original directory to restore later
    original_cwd = os.getcwd()

    # Change to tmp_path since some code uses relative paths
    os.chdir(tmp_path)

    # Create required directories
    (tmp_path / "Cache").mkdir()
    (tmp_path / "Time Series").mkdir()
    (tmp_path / "Activities").mkdir()

    try:
        app = create_app(
            database_uri="sqlite:///:memory:",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        app.config["TESTING"] = True
        yield app
    finally:
        os.chdir(original_cwd)


@pytest.fixture
def client(app: Flask):
    """Create a test client for the Flask app."""
    return app.test_client()
