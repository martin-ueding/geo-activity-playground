"""The steps that sources share when a remote API hands out one file per activity.

The API lists activities and describes them with a summary. For each one that is new,
the file (usually FIT, but GPX and TCX are possible) is downloaded and kept next to
the summary. Keeping both is what lets
the ingest stage run again later without going back to the API.
"""

import dataclasses
import datetime
import json
import logging
import pathlib
from collections.abc import Callable
from typing import Any

import sqlalchemy

from ..importers.activity_parsers import ActivityParseError, read_activity
from .datamodel import (
    DB,
    Activity,
    ActivityImportConfig,
    get_or_make_kind,
    materialize_metadata,
)
from .duplicate_matching import check_for_duplicate
from .enrichment import update_and_commit
from .import_exclusion import is_excluded, record_exclusion
from .paths import atomic_open
from .pipeline import ingest_parsed_activity, keep_trim_indices

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ApiMetadata:
    """What the API states about an activity, beyond what the FIT file contains."""

    name: str | None = None
    kind: str | None = None
    distance_km: float | None = None
    elapsed_time: datetime.timedelta | None = None


def already_imported(source: str, upstream_id: str) -> bool:
    """Whether the activity is in the database or was excluded from import."""
    if is_excluded(source, upstream_id):
        return True
    existing = DB.session.scalar(
        sqlalchemy.select(Activity).where(Activity.upstream_id == upstream_id)
    )
    return existing is not None


def newest_date(current: str | None, candidate: str) -> str:
    """The later of two ISO dates, where `current` may not exist yet."""
    if current is None or candidate > current:
        return candidate
    return current


def stored_file_path(directory: pathlib.Path, upstream_id: str) -> pathlib.Path:
    """Where the file that the API handed out for this activity is kept.

    The format is whatever the API had, so the file is found by its stem. A FIT file
    is assumed for an activity that has no file yet.
    """
    for path in sorted(directory.glob(f"{upstream_id}.*")):
        if path.suffix.lower() != ".json":
            return path
    return directory / f"{upstream_id}.fit"


def stored_summary_path(directory: pathlib.Path, upstream_id: str) -> pathlib.Path:
    """Where the API's own description of this activity is kept."""
    return directory / f"{upstream_id}.json"


def store_artifacts(
    directory: pathlib.Path,
    upstream_id: str,
    file_bytes: bytes,
    payload: dict[str, Any],
    suffix: str = ".fit",
) -> None:
    """Keep the file and the API's description of the activity.

    Without them the ingest stage could never run again without going back to the
    API, which would make improved parsers unable to reach activities that are
    already imported.
    """
    with atomic_open(directory / f"{upstream_id}{suffix}", "wb") as f:
        f.write(file_bytes)
    with atomic_open(stored_summary_path(directory, upstream_id), "w") as f:
        json.dump(payload, f)


def import_stored_file(
    config: ActivityImportConfig,
    *,
    source: str,
    ingest_version: int,
    directory: pathlib.Path,
    upstream_id: str,
    metadata: ApiMetadata,
) -> bool:
    """Parse the kept file of a new activity and add it to the database.

    Returns False when the activity has no geographic data, which is recorded as an
    exclusion so that it is not downloaded again.
    """
    activity, time_series = read_activity(stored_file_path(directory, upstream_id))

    if len(time_series) == 0 or "latitude" not in time_series.columns:
        logger.warning(
            f"{source} activity {upstream_id} has no geographic data, skipping."
        )
        record_exclusion(source, upstream_id, "no_geo_data")
        return False

    activity.upstream_id = upstream_id
    if metadata.name:
        activity.name_from_file = metadata.name
    if metadata.kind:
        activity.kind_from_file = metadata.kind
    materialize_metadata(activity)
    if metadata.distance_km is not None:
        activity.distance_km = metadata.distance_km
    if metadata.elapsed_time is not None:
        activity.elapsed_time = metadata.elapsed_time
    activity.source = source
    activity.ingest_version = ingest_version

    update_and_commit(activity, time_series, config)
    check_for_duplicate(activity, config)
    logger.info(f"Added activity '{activity.name}' from {source}.")
    return True


def reingest_stored_file(
    activity: Activity,
    config: ActivityImportConfig,
    *,
    directory: pathlib.Path,
    ingest_version: int,
    read_metadata: Callable[[dict[str, Any]], ApiMetadata],
) -> bool:
    """Run the ingest stage again from the kept file and summary.

    Returns False when the files are not kept or cannot be parsed any more.
    """
    if not activity.upstream_id:
        return False
    file_path = stored_file_path(directory, activity.upstream_id)
    summary_path = stored_summary_path(directory, activity.upstream_id)
    if not file_path.exists() or not summary_path.exists():
        logger.warning(
            "Cannot re-ingest %s activity %s, its files are not kept.",
            activity.source,
            activity.id,
        )
        return False

    with open(summary_path) as f:
        metadata = read_metadata(json.load(f))

    try:
        parsed, time_series = read_activity(file_path)
    except ActivityParseError:
        logger.exception("Could not parse %s.", file_path)
        return False

    if metadata.name:
        parsed.name = metadata.name
    if metadata.kind:
        parsed.kind = get_or_make_kind(metadata.kind)

    keep_trim_indices(activity, time_series)
    ingest_parsed_activity(
        activity,
        parsed,
        time_series,
        config,
        ingest_version,
        force_enrichment=True,
    )
    return True
