import logging
import pathlib
import traceback

import pandas as pd
import sqlalchemy
from tqdm import tqdm

from ...core.datamodel import DB, Activity, ActivityImportConfig
from ...core.duplicate_matching import check_for_duplicate
from ...core.import_exclusion import clear_exclusion, is_excluded, record_exclusion
from ...core.pipeline import (
    ACTIVITY_DIR,
    file_sha256,
    file_stat_matches,
    get_metadata_from_path,  # noqa: F401  (re-exported, callers import it from here)
    ingest_parsed_activity,
    keep_trim_indices,
    record_file_stat,
    relocate_activity,
    set_path_metadata,  # noqa: F401  (re-exported, callers import it from here)
)
from ...core.tile_visits import refresh_tile_visits_for_activity
from ...importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
    read_activity,
)

logger = logging.getLogger(__name__)

INGEST_VERSION = 1


def discover_activity_paths(config: ActivityImportConfig) -> list[pathlib.Path]:
    """Stage 0: every file under `Activities` that could hold an activity."""
    paths = [
        path
        for path in ACTIVITY_DIR.rglob("*.*")
        if path.is_file()
        and path.suffixes
        and not path.stem.startswith(".")
        and path.suffix not in config.ignore_suffixes
    ]
    paths.sort()
    return paths


def _backfill_missing_hashes() -> None:
    """Give activities imported before hashing existed their content hash."""
    for activity in DB.session.scalars(
        sqlalchemy.select(Activity).filter(
            Activity.upstream_id.is_(sqlalchemy.null()),
            Activity.path.is_not(sqlalchemy.null()),
        )
    ):
        assert activity.path is not None
        if pathlib.Path(activity.path).exists():
            activity.upstream_id = file_sha256(pathlib.Path(activity.path))
    DB.session.commit()


def import_from_directory(
    config: ActivityImportConfig,
    source: str | None = None,
) -> None:
    """Stage 1: decide for every file whether it is new, moved, changed or current.

    The content hash is the identity of a directory activity and the path is an
    attribute of it. That makes the four cases fall out: a hash nobody knows is a
    new activity, a known hash at a new path is a file that moved, a new hash at a
    known path is a file whose content changed, and anything else is current unless
    the ingest code has moved on.
    """
    _backfill_missing_hashes()

    for path in tqdm(
        discover_activity_paths(config), desc="Importing activity files", delay=1
    ):
        with DB.session.no_autoflush:
            at_this_path = DB.session.scalar(
                sqlalchemy.select(Activity).filter(Activity.path == str(path))
            )
            # A file that still has the size and modification time it was read with
            # cannot have moved or changed, so it need not be hashed at all. This is
            # the case for nearly every file on nearly every scan.
            if at_this_path is not None and file_stat_matches(at_this_path, path):
                continue

            file_hash = file_sha256(path)

            with_same_hash = DB.session.scalars(
                sqlalchemy.select(Activity).filter(Activity.upstream_id == file_hash)
            ).all()
            if len(with_same_hash) > 1:
                logger.warning(
                    "The following activities are duplicates: "
                    + ", ".join(str(activity.id) for activity in with_same_hash)
                )
            if with_same_hash:
                _handle_known_content(with_same_hash[0], path, config)
                continue

            if at_this_path is not None:
                reimport_changed_file(at_this_path, path, file_hash, config)
                continue

            if is_excluded("directory", file_hash):
                continue

            import_from_file(path, config, file_hash, source)


def _handle_known_content(
    activity: Activity, path: pathlib.Path, config: ActivityImportConfig
) -> None:
    """The content is already imported, so only a move is left to notice here."""
    if activity.path == str(path):
        # Same content at the same place; only the modification time moved.
        record_file_stat(activity, path)
        DB.session.commit()
        return
    # A second file with the same content is a copy, not a move. Only treat it as a
    # move once the file that this activity points at is gone.
    if activity.path is None or not pathlib.Path(activity.path).exists():
        relocate_activity(activity, path, config)


def reingest_activity(activity: Activity, config: ActivityImportConfig) -> bool:
    """Run stage 1 again for an activity whose file has not changed.

    This is what a raised `INGEST_VERSION` triggers: the parsers extract something
    they did not extract before, so the file has to be read again. User edits live in
    their own layer and are untouched.
    """
    if activity.path is None:
        return False
    path = pathlib.Path(activity.path)
    if not path.exists():
        logger.warning("Cannot re-ingest activity %s, %s is gone.", activity.id, path)
        return False

    parsed = _parse(path, activity.upstream_id or "")
    if parsed is None:
        return False
    parsed_activity, time_series = parsed

    keep_trim_indices(activity, time_series)
    record_file_stat(activity, path)
    ingest_parsed_activity(
        activity,
        parsed_activity,
        time_series,
        config,
        INGEST_VERSION,
        force_enrichment=True,
    )
    return True


def reimport_changed_file(
    activity: Activity,
    path: pathlib.Path,
    file_hash: str,
    config: ActivityImportConfig,
) -> None:
    """The file at a known path holds different content than it did before.

    The activity keeps its identity in the database -- its tags, photos, segment
    matches and user edits -- and takes on the new content.
    """
    logger.info("The file %s changed, re-importing activity %s.", path, activity.id)
    parsed = _parse(path, file_hash)
    if parsed is None:
        return
    parsed_activity, time_series = parsed

    keep_trim_indices(activity, time_series)
    record_file_stat(activity, path)
    clear_exclusion("directory", file_hash)
    activity.upstream_id = file_hash
    ingest_parsed_activity(
        activity,
        parsed_activity,
        time_series,
        config,
        INGEST_VERSION,
        force_enrichment=True,
    )
    refresh_tile_visits_for_activity(activity.id)


def _parse(path: pathlib.Path, file_hash: str) -> tuple[Activity, pd.DataFrame] | None:
    """Stage 1 proper: a file becomes an activity and a time series, or an exclusion."""
    try:
        activity, time_series = read_activity(path)
    except NoGeoDataError as e:
        logger.warning(
            f"Activity with {path=} has no geospatial series data, skipping."
        )
        record_exclusion(
            "directory", file_hash, "no_geo_data", path=str(path), error_message=str(e)
        )
        return None
    except ActivityParseError as e:
        logger.error(f"Error while parsing file {path}:")
        traceback.print_exc()
        record_exclusion(
            "directory", file_hash, "parse_error", path=str(path), error_message=str(e)
        )
        return None
    except:
        logger.error(f"Encountered a problem with {path=}, see details below.")
        raise

    if len(time_series) == 0:
        logger.warning(f"Activity with {path=} has no time series data, skipping.")
        record_exclusion("directory", file_hash, "empty_time_series", path=str(path))
        return None

    return activity, time_series


def import_from_file(
    path: pathlib.Path,
    config: ActivityImportConfig,
    file_hash: str,
    source: str | None = None,
) -> None:
    logger.info(f"Importing {path} …")
    parsed = _parse(path, file_hash)
    if parsed is None:
        return
    activity, time_series = parsed

    clear_exclusion("directory", file_hash)

    activity.path = str(path)
    activity.upstream_id = file_hash
    activity.source = source
    record_file_stat(activity, path)
    ingest_parsed_activity(activity, activity, time_series, config, INGEST_VERSION)
    check_for_duplicate(activity, config)
