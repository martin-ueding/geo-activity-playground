import logging
import pathlib
import re
import traceback

import sqlalchemy

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

    for i, activity_path in enumerate(activity_paths):
        with DB.session.no_autoflush:
            activity = DB.session.scalar(
                sqlalchemy.select(Activity).filter(Activity.path == str(activity_path))
            )
            if activity is None:
                import_from_file(
                    activity_path, repository, tile_visit_accessor, config, i
                )


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
