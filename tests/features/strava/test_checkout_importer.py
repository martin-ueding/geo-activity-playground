import pytest
import sqlalchemy

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity, ActivityImportConfig
from geo_activity_playground.core.scan import refresh_stale_ingests
from geo_activity_playground.features.strava.checkout_importer import (
    import_from_strava_checkout,
)
from geo_activity_playground.features.strava.upstream import API_SOURCE, EXPORT_SOURCE
from geo_activity_playground.importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
)
from geo_activity_playground.webui.app import create_app


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


GPX_WITHOUT_NAME = (
    '<?xml version="1.0"?>'
    '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
    "<trk><trkseg>"
    + "".join(
        f'<trkpt lat="50.{i:04d}" lon="7.{i:04d}"><time>2026-01-01T00:{i:02d}:00Z</time></trkpt>'
        for i in range(10)
    )
    + "</trkseg></trk></gpx>"
)


def _write_checkout(tmp_path) -> None:
    checkout_dir = tmp_path / "Strava Export"
    (checkout_dir / "activities").mkdir(parents=True)
    (checkout_dir / "activities" / "123.gpx").write_text(GPX_WITHOUT_NAME)
    (checkout_dir / "activities.csv").write_text(
        "Activity ID,Activity Date,Activity Name,Activity Type,Elapsed Time,Distance,"
        "Calories,Activity Gear,Bike,Gear,Total Steps,Filename\n"
        "123,2026-01-01 00:00:00,Sunday Squadrats,Ride,600,5,0,,,,,activities/123.gpx\n",
        encoding="utf-8",
    )


def _only_activity() -> Activity:
    return DB.session.scalars(sqlalchemy.select(Activity)).one()


def test_scan_keeps_names_from_csv(app_context, tmp_path) -> None:
    _write_checkout(tmp_path)

    import_from_strava_checkout(ActivityImportConfig(), source=EXPORT_SOURCE)
    assert refresh_stale_ingests(ConfigAccessor()) == (0, 0)

    activity = _only_activity()
    assert activity.name == "Sunday Squadrats"
    assert activity.kind.name == "Ride"


def test_reingest_restores_names_from_csv(app_context, tmp_path) -> None:
    _write_checkout(tmp_path)
    import_from_strava_checkout(ActivityImportConfig(), source=EXPORT_SOURCE)
    activity = _only_activity()
    activity.name_from_file = None
    activity.kind_from_file = None
    activity.ingest_version = 1
    DB.session.commit()

    assert refresh_stale_ingests(ConfigAccessor()) == (1, 0)

    activity = _only_activity()
    assert activity.name == "Sunday Squadrats"
    assert activity.kind.name == "Ride"


def test_activity_from_api_is_not_imported_again(app_context, tmp_path) -> None:
    _write_checkout(tmp_path)
    DB.session.add(Activity(name="From API", upstream_id="123", source=API_SOURCE))
    DB.session.commit()

    import_from_strava_checkout(ActivityImportConfig(), source=EXPORT_SOURCE)

    assert _only_activity().source == API_SOURCE
