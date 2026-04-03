from geo_activity_playground.core.config import Config

from .activity_parsers import ActivityParseError, NoGeoDataError
from .strava_checkout import import_from_strava_checkout


def test_no_geo_data_errors_are_marked_done(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

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
        "geo_activity_playground.importers.strava_checkout.read_activity",
        fake_read_activity,
    )

    import_from_strava_checkout(Config())
    import_from_strava_checkout(Config())

    assert calls == 1


def test_other_parse_errors_are_retried(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

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
        "geo_activity_playground.importers.strava_checkout.read_activity",
        fake_read_activity,
    )

    import_from_strava_checkout(Config())
    import_from_strava_checkout(Config())

    assert calls == 2
