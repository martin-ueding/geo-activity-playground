import datetime
import hashlib
import logging
import pathlib
import re
import traceback

import sqlalchemy
from tqdm import tqdm

from ...core.activities import ActivityRepository
from ...core.datamodel import (
    DB,
    DEFAULT_UNKNOWN_NAME,
    Activity,
    ActivityImportConfig,
    UiConfig,
    get_or_make_equipment,
    get_or_make_kind,
)
from ...core.enrichment import update_and_commit
from ...explorer.tile_visits import (
    compute_tile_evolution,
    compute_tile_visits_new,
)
from ...importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
    read_activity,
)
from .model import BrokenActivityFile

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def import_from_directory(
    repository: ActivityRepository,
    config: ActivityImportConfig,
    ui_config: UiConfig,
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

    for i, activity_path in enumerate(
        tqdm(paths_to_import, desc="Importing activity files", delay=0)
    ):
        with DB.session.no_autoflush:
            activity = DB.session.scalar(
                sqlalchemy.select(Activity).filter(Activity.path == str(activity_path))
            )
            if activity is not None:
                continue

            current_hash = file_sha256(activity_path)

            broken = DB.session.scalar(
                sqlalchemy.select(BrokenActivityFile).filter(
                    BrokenActivityFile.path == str(activity_path)
                )
            )
            if broken is not None and broken.file_hash == current_hash:
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
                activity_path, repository, config, ui_config, i, current_hash
            )


def import_from_file(
    path: pathlib.Path,
    repository: ActivityRepository,
    config: ActivityImportConfig,
    ui_config: UiConfig,
    i: int,
    file_hash: str,
) -> None:
    logger.info(f"Importing {path} …")
    try:
        activity, time_series = read_activity(path)
    except NoGeoDataError as e:
        logger.warning(
            f"Activity with {path=} has no geospatial series data, skipping."
        )
        _record_broken(path, file_hash, "no_geo_data", str(e))
        return
    except ActivityParseError as e:
        logger.error(f"Error while parsing file {path}:")
        traceback.print_exc()
        _record_broken(path, file_hash, "parse_error", str(e))
        return
    except:
        logger.error(f"Encountered a problem with {path=}, see details below.")
        raise

    if len(time_series) == 0:
        logger.warning(f"Activity with {path=} has no time series data, skipping.")
        _record_broken(path, file_hash, "empty_time_series", None)
        return

    _clear_broken(path)

    activity.path = str(path)
    activity.upstream_id = file_hash
    if activity.name is None:
        activity.name = path.name.removesuffix("".join(path.suffixes))

    meta_from_path = get_metadata_from_path(path, config.metadata_extraction_regexes)
    activity.name = meta_from_path.get("name", activity.name)
    if "equipment" in meta_from_path:
        activity.equipment = get_or_make_equipment(meta_from_path["equipment"])
    if "kind" in meta_from_path:
        activity.kind = get_or_make_kind(meta_from_path["kind"])
    if activity.equipment is None:
        activity.equipment = get_or_make_equipment(
            meta_from_path.get("equipment", DEFAULT_UNKNOWN_NAME)
        )
    if activity.kind is None:
        activity.kind = get_or_make_kind(
            meta_from_path.get("kind", DEFAULT_UNKNOWN_NAME)
        )

    update_and_commit(activity, time_series, config)

    if len(repository) > 0 and i % 50 == 0:
        compute_tile_visits_new(repository)
        compute_tile_evolution(ui_config)


def _record_broken(
    path: pathlib.Path, file_hash: str, reason: str, error_message: str | None
) -> None:
    broken = DB.session.scalar(
        sqlalchemy.select(BrokenActivityFile).filter(
            BrokenActivityFile.path == str(path)
        )
    )
    if broken is None:
        broken = BrokenActivityFile(path=str(path))
        DB.session.add(broken)
    broken.file_hash = file_hash
    broken.reason = reason
    broken.error_message = error_message
    broken.last_attempt = datetime.datetime.now(datetime.UTC)
    DB.session.commit()


def _clear_broken(path: pathlib.Path) -> None:
    DB.session.execute(
        sqlalchemy.delete(BrokenActivityFile).where(
            BrokenActivityFile.path == str(path)
        )
    )


def get_metadata_from_path(
    path: pathlib.Path, metadata_extraction_regexes: list[str]
) -> dict[str, str]:
    for regex in metadata_extraction_regexes:
        if m := re.search(regex, str(path.relative_to(ACTIVITY_DIR))):
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
