import hashlib
import logging
import pathlib
import re
import traceback

import sqlalchemy
from tqdm import tqdm

from ...core.datamodel import (
    DB,
    Activity,
    ActivityImportConfig,
    materialize_metadata,
)
from ...core.duplicate_matching import check_for_duplicate
from ...core.enrichment import update_and_commit
from ...core.import_exclusion import clear_exclusion, is_excluded, record_exclusion
from ...importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
    read_activity,
)

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def import_from_directory(
    config: ActivityImportConfig,
    source: str | None = None,
) -> None:
    activity_paths = [
        path
        for path in ACTIVITY_DIR.rglob("*.*")
        if path.is_file()
        and path.suffixes
        and not path.stem.startswith(".")
        and path.suffix not in config.ignore_suffixes
    ]
    activity_paths.sort()

    paths_to_import = [
        activity_path
        for activity_path in tqdm(
            activity_paths, desc="Scanning for new files", delay=1
        )
        if DB.session.scalar(
            sqlalchemy.select(Activity).filter(Activity.path == str(activity_path))
        )
        is None
    ]

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

    for activity_path in tqdm(
        paths_to_import, desc="Importing activity files", delay=0
    ):
        with DB.session.no_autoflush:
            activity = DB.session.scalar(
                sqlalchemy.select(Activity).filter(Activity.path == str(activity_path))
            )
            if activity is not None:
                continue

            current_hash = file_sha256(activity_path)

            if is_excluded("directory", current_hash):
                continue

            with_same_hash = DB.session.scalars(
                sqlalchemy.select(Activity).filter(Activity.upstream_id == current_hash)
            ).all()
            if with_same_hash:
                if len(with_same_hash) == 1:
                    continue
                else:
                    logger.warning(
                        "The following activities are duplicates: "
                        + ", ".join(str(activity.id) for activity in with_same_hash)
                    )

            import_from_file(
                activity_path,
                config,
                current_hash,
                source,
            )


def import_from_file(
    path: pathlib.Path,
    config: ActivityImportConfig,
    file_hash: str,
    source: str | None = None,
) -> None:
    logger.info(f"Importing {path} …")
    try:
        activity, time_series = read_activity(path)
    except NoGeoDataError as e:
        logger.warning(
            f"Activity with {path=} has no geospatial series data, skipping."
        )
        record_exclusion(
            "directory", file_hash, "no_geo_data", path=str(path), error_message=str(e)
        )
        return
    except ActivityParseError as e:
        logger.error(f"Error while parsing file {path}:")
        traceback.print_exc()
        record_exclusion(
            "directory", file_hash, "parse_error", path=str(path), error_message=str(e)
        )
        return
    except:
        logger.error(f"Encountered a problem with {path=}, see details below.")
        raise

    if len(time_series) == 0:
        logger.warning(f"Activity with {path=} has no time series data, skipping.")
        record_exclusion("directory", file_hash, "empty_time_series", path=str(path))
        return

    clear_exclusion("directory", file_hash)

    activity.path = str(path)
    activity.upstream_id = file_hash
    activity.name_from_file = activity.name
    activity.kind_from_file = activity.kind.name if activity.kind is not None else None
    activity.equipment_from_file = (
        activity.equipment.name if activity.equipment is not None else None
    )

    set_path_metadata(activity, config.metadata_extraction_regexes)
    materialize_metadata(activity)
    activity.source = source

    update_and_commit(activity, time_series, config)
    check_for_duplicate(activity, config)


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


def get_metadata_from_path(
    path: pathlib.Path, metadata_extraction_regexes: list[str]
) -> dict[str, str]:
    for regex in metadata_extraction_regexes:
        if m := re.search(regex, path.relative_to(ACTIVITY_DIR).as_posix()):
            return m.groupdict()
    return {}


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
