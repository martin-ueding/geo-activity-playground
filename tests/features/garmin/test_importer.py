import io
import pathlib
import zipfile
from types import SimpleNamespace

import pytest
import sqlalchemy
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.core.import_exclusion import ImportExclusion
from geo_activity_playground.features.garmin import importer
from geo_activity_playground.features.garmin.model import get_garmin_auth

FIT_NAME = "2024-05-10-19-32-04.fit"
REFRESHED_TOKENS = '{"di_token": "refreshed"}'


def _summary(activity_id: int, start: str, **extra) -> dict:
    return {
        "activityId": activity_id,
        "activityName": f"Ride {activity_id}",
        "startTimeGMT": start,
        "activityType": {"typeKey": "cycling"},
        "distance": 1000.0,
        "elapsedDuration": 600.0,
        **extra,
    }


class FakeGarmin:
    """Stands in for the logged-in client, answering from memory."""

    def __init__(
        self, summaries: list[dict], fit_bytes: bytes, suffix: str = ".fit"
    ) -> None:
        self.summaries = summaries
        self.fit_bytes = fit_bytes
        self.suffix = suffix
        self.downloads: list[str] = []
        self.listed_from: list[str] = []
        self.fail_download: dict[str, Exception] = {}
        self.client = SimpleNamespace(dumps=lambda: REFRESHED_TOKENS)

    def get_activities_by_date(self, start, _end, sortorder=None):
        assert sortorder == "asc"
        self.listed_from.append(start)
        return self.summaries

    def download_activity(self, activity_id, **_kwargs):
        self.downloads.append(activity_id)
        if activity_id in self.fail_download:
            raise self.fail_download[activity_id]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(f"{activity_id}_ACTIVITY{self.suffix}", self.fit_bytes)
        return buffer.getvalue()


@pytest.fixture
def fit_bytes(testdata_dir: pathlib.Path) -> bytes:
    return (testdata_dir / "Local Files" / "Activities" / FIT_NAME).read_bytes()


@pytest.fixture
def run_import(app_context, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(importer, "SECONDS_BETWEEN_DOWNLOADS", 0)

    def run(fake: FakeGarmin, **kwargs) -> None:
        monkeypatch.setattr(importer, "create_client", lambda _auth: fake)
        importer.import_from_garmin(ConfigAccessor().activity_import(), **kwargs)

    return run


def _activities() -> list[Activity]:
    return list(DB.session.scalars(sqlalchemy.select(Activity)).all())


def test_extract_activity_file_returns_the_recording(fit_bytes: bytes) -> None:
    fake = FakeGarmin([], fit_bytes)
    assert importer.extract_activity_file(fake.download_activity("1")) == (
        ".fit",
        fit_bytes,
    )


def test_extract_activity_file_accepts_uploaded_gpx() -> None:
    fake = FakeGarmin([], b"<gpx/>", suffix=".gpx")
    assert importer.extract_activity_file(fake.download_activity("1")) == (
        ".gpx",
        b"<gpx/>",
    )


def test_extract_activity_file_rejects_archives_without_a_recording() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "no activity here")
    with pytest.raises(zipfile.BadZipFile):
        importer.extract_activity_file(buffer.getvalue())


def test_activity_that_was_uploaded_as_gpx_is_imported(
    run_import, testdata_dir: pathlib.Path
) -> None:
    gpx = testdata_dir / "Local Files" / "Activities" / "Berlin (0,9 km).gpx"
    fake = FakeGarmin(
        [_summary(444, "2024-05-10 17:32:04")], gpx.read_bytes(), suffix=".gpx"
    )

    run_import(fake)

    (activity,) = _activities()
    assert activity.upstream_id == "444"
    assert activity.source == "garmin"
    assert importer.reingest_garmin_activity(
        activity, ConfigAccessor().activity_import()
    )


def test_import_adds_activity_and_moves_cursor(run_import, fit_bytes: bytes) -> None:
    fake = FakeGarmin([_summary(111, "2024-05-10 17:32:04")], fit_bytes)

    run_import(fake)

    (activity,) = _activities()
    assert activity.source == "garmin"
    assert activity.upstream_id == "111"
    assert activity.name == "Ride 111"
    assert activity.kind.name == "cycling"
    assert activity.ingest_version == importer.INGEST_VERSION
    assert fake.listed_from == ["2000-01-01"]
    assert get_garmin_auth().last_activity_date == "2024-05-10"
    assert get_garmin_auth().token_json == REFRESHED_TOKENS


def test_second_run_starts_at_cursor_and_skips_known_activities(
    run_import, fit_bytes: bytes
) -> None:
    fake = FakeGarmin([_summary(111, "2024-05-10 17:32:04")], fit_bytes)
    run_import(fake)

    run_import(fake)

    assert fake.listed_from == ["2000-01-01", "2024-05-10"]
    assert fake.downloads == ["111"]
    assert len(_activities()) == 1


def test_explicit_range_leaves_cursor_alone(run_import, fit_bytes: bytes) -> None:
    fake = FakeGarmin([_summary(111, "2024-05-10 17:32:04")], fit_bytes)

    run_import(fake, garmin_begin="2024-01-01", garmin_end="2024-12-31")

    assert fake.listed_from == ["2024-01-01"]
    assert len(_activities()) == 1
    assert get_garmin_auth().last_activity_date is None


def test_manual_activity_is_excluded_without_download(
    run_import, fit_bytes: bytes
) -> None:
    fake = FakeGarmin(
        [_summary(222, "2024-05-11 08:00:00", manualActivity=True)], fit_bytes
    )

    run_import(fake)

    assert fake.downloads == []
    assert _activities() == []
    exclusion = DB.session.scalars(sqlalchemy.select(ImportExclusion)).one()
    assert (exclusion.source, exclusion.upstream_id) == ("garmin", "222")


def test_failed_download_keeps_cursor_before_the_failure(
    run_import, fit_bytes: bytes
) -> None:
    fake = FakeGarmin(
        [
            _summary(111, "2024-05-10 17:32:04"),
            _summary(222, "2024-05-11 08:00:00"),
            _summary(333, "2024-05-12 08:00:00"),
        ],
        fit_bytes,
    )
    fake.fail_download["222"] = GarminConnectConnectionError("boom")

    run_import(fake)

    assert get_garmin_auth().last_activity_date == "2024-05-10"
    assert "333" in fake.downloads


def test_rate_limit_stops_the_import_without_raising(
    run_import, fit_bytes: bytes
) -> None:
    fake = FakeGarmin(
        [_summary(111, "2024-05-10 17:32:04"), _summary(222, "2024-05-11 08:00:00")],
        fit_bytes,
    )
    fake.fail_download["111"] = GarminConnectTooManyRequestsError("429")

    run_import(fake)

    assert fake.downloads == ["111"]
    assert get_garmin_auth().last_activity_date is None


def test_rejected_tokens_skip_the_import(
    app_context, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_garmin_auth().token_json = '{"di_token": "stale"}'
    DB.session.commit()

    class RejectingGarmin:
        def login(self, **_kwargs):
            raise GarminConnectAuthenticationError("401")

    monkeypatch.setattr(importer, "Garmin", RejectingGarmin)

    importer.import_from_garmin(ConfigAccessor().activity_import())

    assert _activities() == []


def test_source_is_enabled_only_with_tokens(app_context) -> None:
    from geo_activity_playground.features.garmin.source import GarminActivitySource

    source = GarminActivitySource()
    assert not source.is_enabled(ConfigAccessor())

    get_garmin_auth().token_json = "{}"
    DB.session.commit()
    assert source.is_enabled(ConfigAccessor())


def test_reingest_reads_kept_files(run_import, fit_bytes: bytes) -> None:
    fake = FakeGarmin([_summary(111, "2024-05-10 17:32:04")], fit_bytes)
    run_import(fake)
    (activity,) = _activities()

    assert importer.reingest_garmin_activity(
        activity, ConfigAccessor().activity_import()
    )
    assert activity.name == "Ride 111"
