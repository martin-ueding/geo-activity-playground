"""The stages that turn an upstream artifact into a stored activity.

The pipeline runs in five stages, each with its own trigger for running again:

1. **parse** -- the upstream artifact becomes a time series plus the metadata that
   the artifact itself states. Runs for a new activity, for changed content, and
   when the source's ``ingest_version`` has moved on. Needs the artifact, so it
   only works where the source kept one.
2. **file metadata** -- what the artifact stated is recorded in the file layer.
3. **path metadata** -- the configured regexes fill the path layer, and the layers
   are resolved into the columns everything else reads. Runs when the file moves or
   the regexes change; needs nothing but the database.
4. **enrich** -- derived columns and summary fields are computed from the time
   series. Each step carries its own version and runs again when that version
   moves on; needs the stored time series, never the artifact.
5. **persist** -- the time series and the row are written.

Stage 3 never overwrites the user layer, and stage 4 works off stored data, so the
only stage that can be blocked by a missing artifact is stage 1.
"""

import hashlib
import logging
import pathlib
import re

import pandas as pd
import sqlalchemy

from .datamodel import DB, Activity, ActivityImportConfig, materialize_metadata
from .enrichment import enrichments, update_and_commit

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def file_sha256(filename: pathlib.Path) -> str:
    """
    Based on https://stackoverflow.com/a/44873382/653152.
    """
    h = hashlib.sha256(usedforsecurity=False)
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()


def get_metadata_from_path(
    path: pathlib.Path, metadata_extraction_regexes: list[str]
) -> dict[str, str]:
    for regex in metadata_extraction_regexes:
        if m := re.search(regex, path.relative_to(ACTIVITY_DIR).as_posix()):
            return m.groupdict()
    return {}


def set_path_metadata(
    activity: Activity, metadata_extraction_regexes: list[str]
) -> None:
    """Refresh the path layer of an activity from the configured regexes."""
    meta = (
        get_metadata_from_path(pathlib.Path(activity.path), metadata_extraction_regexes)
        if activity.path
        else {}
    )
    activity.name_from_path = meta.get("name")
    activity.kind_from_path = meta.get("kind")
    activity.equipment_from_path = meta.get("equipment")


def stage_file_metadata(activity: Activity, parsed: Activity) -> None:
    """Record what the artifact itself stated about the activity."""
    activity.name_from_file = parsed.name
    activity.kind_from_file = parsed.kind.name if parsed.kind is not None else None
    if parsed.equipment is not None:
        activity.equipment_from_file = parsed.equipment.name


def stage_path_metadata(activity: Activity, config: ActivityImportConfig) -> None:
    """Refresh the path layer and resolve all layers into the read columns."""
    set_path_metadata(activity, config.metadata_extraction_regexes)
    materialize_metadata(activity)


def stage_persist(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool = False,
) -> None:
    """Run the enrichments and write the activity out."""
    update_and_commit(activity, time_series, config, force=force)


def keep_trim_indices(activity: Activity, time_series: pd.DataFrame) -> None:
    """Drop the trim indices when they can no longer mean what they meant.

    The indices are positions into the time series. A time series of unchanged
    length is assumed to still be the same recording, so the trim survives; any
    other length makes the positions meaningless and the trim is reset.
    """
    if activity.index_begin is None and activity.index_end is None:
        return
    previous = activity.raw_time_series
    if previous is None or len(previous) != len(time_series):
        logger.info(
            "Resetting the trim of activity %s, the time series changed length.",
            activity.id,
        )
        activity.index_begin = None
        activity.index_end = None


def ingest_parsed_activity(
    activity: Activity,
    parsed: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    ingest_version: int,
    force_enrichment: bool = False,
) -> None:
    """Stages 2 to 5 for an activity whose artifact has just been parsed."""
    stage_file_metadata(activity, parsed)
    stage_path_metadata(activity, config)
    activity.ingest_version = ingest_version
    stage_persist(activity, time_series, config, force=force_enrichment)


def relocate_activity(
    activity: Activity, path: pathlib.Path, config: ActivityImportConfig
) -> None:
    """Follow a file that moved: the content is known, only the path is new.

    Only stage 3 has to run, because the content that stages 1, 2 and 4 work on is
    unchanged. The path layer is refreshed, so sorting a file into a directory tree
    that encodes kind and equipment reaches the activity that is already imported.
    """
    logger.info("Activity %s moved from %r to %r.", activity.id, activity.path, path)
    activity.path = str(path)
    stage_path_metadata(activity, config)
    DB.session.commit()


def current_enrichment_versions() -> dict[str, int]:
    return {
        enrichment.__name__: getattr(enrichment, "version", 1)
        for enrichment in enrichments
    }


def refresh_stale_enrichments(config: ActivityImportConfig) -> int:
    """Re-run the enrichments of every activity whose stamps lag behind the code.

    This is the cheap half of catching up: enrichments read the stored time series,
    so nothing has to be parsed again and no source file has to be present.
    """
    current = current_enrichment_versions()
    stale = [
        activity
        for activity in DB.session.scalars(sqlalchemy.select(Activity)).all()
        if any(
            (activity.enrichment_versions or {}).get(name) != version
            for name, version in current.items()
        )
    ]
    if not stale:
        return 0

    logger.info("Re-running enrichments for %d activities.", len(stale))
    refreshed = 0
    for activity in stale:
        time_series = activity.raw_time_series
        if time_series is None or len(time_series) < 2:
            continue
        update_and_commit(activity, time_series, config)
        refreshed += 1
    return refreshed
