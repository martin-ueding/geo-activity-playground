import hashlib
import logging
import pathlib
import pickle
import re
import sys
import traceback

import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activity_parsers import ActivityParseError
from geo_activity_playground.core.activity_parsers import read_activity
from geo_activity_playground.core.tasks import WorkTracker

logger = logging.getLogger(__name__)


def import_from_directory(
    repository: ActivityRepository, meta_data_extraction_regexes: list[str] = []
) -> None:
    paths_with_errors = []
    work_tracker = WorkTracker("parse-activity-files")
    activity_dir = pathlib.Path("Activities")

    activity_paths = [
        path
        for path in activity_dir.rglob("*.*")
        if path.is_file() and path.suffixes and not path.stem.startswith(".")
    ]
    new_activity_paths = work_tracker.filter(activity_paths)

    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    activity_stream_dir.mkdir(exist_ok=True, parents=True)
    file_metadata_dir = pathlib.Path("Cache/Activity Metadata")
    file_metadata_dir.mkdir(exist_ok=True, parents=True)

    for path in tqdm(new_activity_paths, desc="Parse activity files"):
        activity_id = _get_file_hash(path)
        timeseries_path = activity_stream_dir / f"{activity_id}.parquet"
        file_metadata_path = file_metadata_dir / f"{activity_id}.pickle"
        work_tracker.mark_done(path)

        if not timeseries_path.exists():
            try:
                activity_meta_from_file, timeseries = read_activity(path)
            except ActivityParseError as e:
                logger.error(f"Error while parsing file {path}:")
                traceback.print_exc()
                paths_with_errors.append((path, str(e)))
                continue
            except:
                logger.error(f"Encountered a problem with {path=}, see details below.")
                raise

            if len(timeseries) == 0:
                continue

            timeseries.to_parquet(timeseries_path)
            with open(file_metadata_path, "wb") as f:
                pickle.dump(activity_meta_from_file, f)
        else:
            with open(file_metadata_path, "rb") as f:
                activity_meta_from_file = pickle.load(f)

        activity_meta = ActivityMeta(
            id=activity_id,
            # https://stackoverflow.com/a/74718395/653152
            name=path.name.removesuffix("".join(path.suffixes)),
            path=str(path),
            kind="Unknown",
            equipment="Unknown",
        )
        activity_meta.update(activity_meta_from_file)
        for regex in meta_data_extraction_regexes:
            if m := re.search(regex, str(path.relative_to(activity_dir))):
                activity_meta.update(m.groupdict())
                break

        repository.add_activity(activity_meta)

    if paths_with_errors:
        logger.warning(
            "There were errors while parsing some of the files. These were skipped and tried again next time."
        )
        for path, error in paths_with_errors:
            logger.error(f"{path}: {error}")

    repository.commit()

    work_tracker.close()


def _get_file_hash(path: pathlib.Path) -> int:
    file_hash = hashlib.blake2s()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            file_hash.update(chunk)
    return int(file_hash.hexdigest(), 16) % 2**62
