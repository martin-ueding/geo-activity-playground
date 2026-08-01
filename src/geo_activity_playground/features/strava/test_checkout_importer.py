import pytest

from geo_activity_playground.core.datamodel import ActivityImportConfig
from geo_activity_playground.importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
)
from geo_activity_playground.webui.app import create_app

from .checkout_importer import import_from_strava_checkout


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(database_uri="sqlite:///:memory:", run_migrations=False)
    with app.app_context():
        yield


def test_no_geo_data_errors_are_marked_done(app_context, monkeypatch, tmp_path) -> None:
    checkout_dir = tmp_path / "Strava Export"
    checkout_dir.mkdir()
    (checkout_dir / "activities.csv").write_text(
        "Activity ID,Activity Date,Filename\n1,2026-01-01 00:00:00,error.gpx\n",
        encoding="utf-8",
    )

    calls = 0

    def fake_read_activity(_path):
        nonlocal calls
        calls += 1
        raise NoGeoDataError("latitude is mandatory in None (got None)")

    monkeypatch.setattr(
        "geo_activity_playground.features.strava.checkout_importer.read_activity",
        fake_read_activity,
    )

    import_from_strava_checkout(ActivityImportConfig(), source="strava")
    import_from_strava_checkout(ActivityImportConfig(), source="strava")

    assert calls == 1


def test_other_parse_errors_are_retried(app_context, monkeypatch, tmp_path) -> None:
    checkout_dir = tmp_path / "Strava Export"
    checkout_dir.mkdir()
    (checkout_dir / "activities.csv").write_text(
        "Activity ID,Activity Date,Filename\n1,2026-01-01 00:00:00,error.gpx\n",
        encoding="utf-8",
    )

    calls = 0

    def fake_read_activity(_path):
        nonlocal calls
        calls += 1
        raise ActivityParseError("invalid input")

    monkeypatch.setattr(
        "geo_activity_playground.features.strava.checkout_importer.read_activity",
        fake_read_activity,
    )

    import_from_strava_checkout(ActivityImportConfig(), source="strava")
    import_from_strava_checkout(ActivityImportConfig(), source="strava")

    assert calls == 2
