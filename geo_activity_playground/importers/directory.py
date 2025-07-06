import hashlib
import logging
import pathlib
import pickle
import re
import traceback
from typing import Optional

import sqlalchemy
from tqdm import tqdm

from ..core.config import Config
from ..core.datamodel import Activity
from ..core.datamodel import ActivityMeta
from ..core.datamodel import DB
from ..core.datamodel import DEFAULT_UNKNOWN_NAME
from ..core.datamodel import get_or_make_equipment
from ..core.datamodel import get_or_make_kind
from ..core.enrichment import apply_enrichments
from ..core.paths import activity_extracted_dir
from ..core.paths import activity_extracted_meta_dir
from ..core.paths import activity_extracted_time_series_dir
from ..core.tasks import stored_object
from ..core.tasks import WorkTracker
from .activity_parsers import ActivityParseError
from .activity_parsers import read_activity

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def import_from_directory(config: Config) -> None:
    activity_paths = [
        path
        for path in ACTIVITY_DIR.rglob("*.*")
        if path.is_file()
        and path.suffixes
        and not path.stem.startswith(".")
        and not path.suffix in config.ignore_suffixes
    ]

    for activity_path in activity_paths:
        with DB.session.no_autoflush:
            activity = DB.session.scalar(
                sqlalchemy.select(Activity).filter(Activity.path == str(activity_path))
            )
            if activity is None:
                import_from_file(activity_path, config)


def import_from_file(path: pathlib.Path, config: Config) -> None:
    logger.info(f"Importing {path=}")
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
    if activity.equipment is None:
        activity.equipment = get_or_make_equipment(
            meta_from_path.get("equipment", DEFAULT_UNKNOWN_NAME), config
        )
    if activity.kind is None:
        activity.kind = get_or_make_kind(
            meta_from_path.get("kind", DEFAULT_UNKNOWN_NAME)
        )

    apply_enrichments(activity, time_series, config)
    DB.session.add(activity)
    DB.session.commit()
    activity.replace_time_series(time_series)


def _get_metadata_from_path(
    path: pathlib.Path, metadata_extraction_regexes: list[str]
) -> dict[str, str]:
    for regex in metadata_extraction_regexes:
        if m := re.search(regex, str(path.relative_to(ACTIVITY_DIR))):
            return m.groupdict()
    return {}
