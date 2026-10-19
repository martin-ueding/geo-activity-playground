import pathlib

import sqlalchemy

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.core.fit_api_import import (
    FitApiMetadata,
    already_imported,
    import_stored_fit,
    newest_date,
    reingest_stored_fit,
    store_artifacts,
    stored_fit_path,
    stored_summary_path,
)
from geo_activity_playground.core.import_exclusion import record_exclusion

SOURCE = "example"
FIT_NAME = "2024-05-10-19-32-04.fit"


def _fit_bytes(testdata_dir: pathlib.Path) -> bytes:
    return (testdata_dir / "Local Files" / "Activities" / FIT_NAME).read_bytes()


def _metadata_from(payload: dict) -> FitApiMetadata:
    return FitApiMetadata(name=payload["name"], kind=payload["kind"])


def test_newest_date_picks_newer() -> None:
    assert newest_date(None, "2026-01-01T00:00:00Z") == "2026-01-01T00:00:00Z"
    assert (
        newest_date("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
        == "2026-02-01T00:00:00Z"
    )
    assert (
        newest_date("2026-02-01T00:00:00Z", "2026-01-01T00:00:00Z")
        == "2026-02-01T00:00:00Z"
    )


def test_store_artifacts_keeps_both_files(
    playground: pathlib.Path, testdata_dir: pathlib.Path
) -> None:
    directory = playground / "Cache" / "Example"
    directory.mkdir()
    fit_bytes = _fit_bytes(testdata_dir)

    store_artifacts(directory, "42", fit_bytes, {"name": "Morning ride"})

    assert stored_fit_path(directory, "42").read_bytes() == fit_bytes
    assert '"Morning ride"' in stored_summary_path(directory, "42").read_text()


def test_import_stored_fit_then_reingest(
    app_context: None, playground: pathlib.Path, testdata_dir: pathlib.Path
) -> None:
    directory = playground / "Cache" / "Example"
    directory.mkdir()
    config = ConfigAccessor().activity_import()
    payload = {"name": "Morning ride", "kind": "Ride"}
    store_artifacts(directory, "42", _fit_bytes(testdata_dir), payload)

    assert not already_imported(SOURCE, "42")
    assert import_stored_fit(
        config,
        source=SOURCE,
        ingest_version=3,
        directory=directory,
        upstream_id="42",
        metadata=_metadata_from(payload),
    )
    assert already_imported(SOURCE, "42")

    activity = DB.session.scalars(sqlalchemy.select(Activity)).one()
    assert activity.upstream_id == "42"
    assert activity.source == SOURCE
    assert activity.name == "Morning ride"
    assert activity.kind.name == "Ride"
    assert activity.ingest_version == 3

    # The summary changed upstream, and the second ingest reads it from the disk.
    store_artifacts(
        directory,
        "42",
        _fit_bytes(testdata_dir),
        {"name": "Renamed ride", "kind": "Ride"},
    )
    assert reingest_stored_fit(
        activity,
        config,
        directory=directory,
        ingest_version=4,
        read_metadata=_metadata_from,
    )
    assert activity.name == "Renamed ride"
    assert activity.ingest_version == 4


def test_reingest_without_kept_files_reports_failure(
    app_context: None, playground: pathlib.Path
) -> None:
    activity = Activity(upstream_id="42", source=SOURCE)
    assert not reingest_stored_fit(
        activity,
        ConfigAccessor().activity_import(),
        directory=playground,
        ingest_version=1,
        read_metadata=_metadata_from,
    )


def test_excluded_activity_counts_as_imported(app_context: None) -> None:
    record_exclusion(SOURCE, "7", "deleted_by_user")
    assert already_imported(SOURCE, "7")
    assert not already_imported("other", "7")
