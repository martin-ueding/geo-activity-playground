import hashlib
import logging
import multiprocessing
import pathlib
import pickle
import re
import sys
import traceback
from typing import Any
from typing import Optional

import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activity_parsers import ActivityParseError
from geo_activity_playground.core.activity_parsers import read_activity
from geo_activity_playground.core.tasks import WorkTracker

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def import_from_directory(
    repository: ActivityRepository,
    kind_defaults: dict[str, Any] = {},
    metadata_extraction_regexes: list[str] = [],
) -> None:
    paths_with_errors = []
    work_tracker = WorkTracker("parse-activity-files")

    activity_paths = [
        path
        for path in ACTIVITY_DIR.rglob("*.*")
        if path.is_file() and path.suffixes and not path.stem.startswith(".")
    ]
    new_activity_paths = work_tracker.filter(activity_paths)

    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    activity_stream_dir.mkdir(exist_ok=True, parents=True)
    file_metadata_dir = pathlib.Path("Cache/Activity Metadata")
    file_metadata_dir.mkdir(exist_ok=True, parents=True)

    with multiprocessing.Pool() as pool:
        paths_with_errors = tqdm(
            pool.imap(_cache_single_file, new_activity_paths),
            desc="Parse activity metadata",
            total=len(new_activity_paths),
        )
        paths_with_errors = [error for error in paths_with_errors if error]

    for path in tqdm(new_activity_paths, desc="Collate activity metadata"):
        activity_id = get_file_hash(path)
        file_metadata_path = file_metadata_dir / f"{activity_id}.pickle"
        work_tracker.mark_done(path)

        if not file_metadata_path.exists():
            continue

        with open(file_metadata_path, "rb") as f:
            activity_meta_from_file = pickle.load(f)

        activity_meta = ActivityMeta(
            id=activity_id,
            # https://stackoverflow.com/a/74718395/653152
            name=path.name.removesuffix("".join(path.suffixes)),
            path=str(path),
            kind="Unknown",
            equipment="Unknown",
            consider_for_achievements=True,
        )
        activity_meta.update(activity_meta_from_file)
        activity_meta.update(_get_metadata_from_path(path, metadata_extraction_regexes))
        activity_meta.update(kind_defaults.get(activity_meta["kind"], {}))
        repository.add_activity(activity_meta)

    if paths_with_errors:
        logger.warning(
            "There were errors while parsing some of the files. These were skipped and tried again next time."
        )
        for path, error in paths_with_errors:
            logger.error(f"{path}: {error}")

    repository.commit()

    work_tracker.close()


def _cache_single_file(path: pathlib.Path) -> Optional[tuple[pathlib.Path, str]]:
    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    file_metadata_dir = pathlib.Path("Cache/Activity Metadata")

    activity_id = get_file_hash(path)
    timeseries_path = activity_stream_dir / f"{activity_id}.parquet"
    file_metadata_path = file_metadata_dir / f"{activity_id}.pickle"

    if not timeseries_path.exists():
        try:
            activity_meta_from_file, timeseries = read_activity(path)
        except ActivityParseError as e:
            logger.error(f"Error while parsing file {path}:")
            traceback.print_exc()
            return path, str(e)
        except:
            logger.error(f"Encountered a problem with {path=}, see details below.")
            raise

        if len(timeseries) == 0:
            return

        timeseries.to_parquet(timeseries_path)
        with open(file_metadata_path, "wb") as f:
            pickle.dump(activity_meta_from_file, f)


def get_file_hash(path: pathlib.Path) -> int:
    file_hash = hashlib.blake2s()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            file_hash.update(chunk)
    return int(file_hash.hexdigest(), 16) % 2**62


def _get_metadata_from_path(
    path: pathlib.Path, metadata_extraction_regexes: list[str]
) -> dict[str, str]:
    for regex in metadata_extraction_regexes:
        if m := re.search(regex, str(path.relative_to(ACTIVITY_DIR))):
            return m.groupdict()
    return {}
