import hashlib
import logging
import pathlib
import re
import traceback

import sqlalchemy
from tqdm import tqdm

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.datamodel import Activity
from ..core.datamodel import DB
from ..core.datamodel import DEFAULT_UNKNOWN_NAME
from ..core.datamodel import get_or_make_equipment
from ..core.datamodel import get_or_make_kind
from ..core.enrichment import update_and_commit
from ..explorer.tile_visits import compute_tile_evolution
from ..explorer.tile_visits import compute_tile_visits_new
from ..explorer.tile_visits import TileVisitAccessor
from .activity_parsers import ActivityParseError
from .activity_parsers import read_activity

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def import_from_directory(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
) -> None:
    activity_paths = [
        path
        for path in ACTIVITY_DIR.rglob("*.*")
        if path.is_file()
        and path.suffixes
        and not path.stem.startswith(".")
        and not path.suffix in config.ignore_suffixes
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

            with_same_hash = DB.session.scalars(
                sqlalchemy.select(Activity).filter(
                    Activity.upstream_id == file_sha256(activity_path)
                )
            ).all()
            if with_same_hash:
                if len(with_same_hash) == 1:
                    continue
                else:
                    logger.warning(
                        "The following activities are duplicates: "
                        + ", ".join(str(activity.id) for activity in with_same_hash)
                    )

            import_from_file(activity_path, repository, tile_visit_accessor, config, i)


def import_from_file(
    path: pathlib.Path,
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    i: int,
) -> None:
    logger.info(f"Importing {path} …")
    try:
        activity, time_series = read_activity(path)
    except ActivityParseError as e:
        logger.error(f"Error while parsing file {path}:")
        traceback.print_exc()
        return
    except:
        logger.error(f"Encountered a problem with {path=}, see details below.")
        raise

    if len(time_series) == 0:
        logger.warning(f"Activity with {path=} has no time series data, skipping.")
        return

    activity.path = str(path)
    activity.upstream_id = file_sha256(path)
    if activity.name is None:
        activity.name = path.name.removesuffix("".join(path.suffixes))

    meta_from_path = _get_metadata_from_path(path, config.metadata_extraction_regexes)
    activity.name = meta_from_path.get("name", activity.name)
    if "equipment" in meta_from_path:
        activity.equipment = get_or_make_equipment(meta_from_path["equipment"], config)
    if "kind" in meta_from_path:
        activity.kind = get_or_make_kind(meta_from_path["kind"])
    if activity.equipment is None:
        activity.equipment = get_or_make_equipment(
            meta_from_path.get("equipment", DEFAULT_UNKNOWN_NAME), config
        )
    if activity.kind is None:
        activity.kind = get_or_make_kind(
            meta_from_path.get("kind", DEFAULT_UNKNOWN_NAME)
        )

    update_and_commit(activity, time_series, config)

    if len(repository) > 0 and i % 50 == 0:
        compute_tile_visits_new(repository, tile_visit_accessor)
        compute_tile_evolution(tile_visit_accessor.tile_state, config)
        tile_visit_accessor.save()


def _get_metadata_from_path(
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
