import hashlib
import logging
import multiprocessing
import pathlib
import pickle
import re
import traceback
from typing import Optional

from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.paths import activity_extracted_dir
from geo_activity_playground.core.paths import activity_extracted_meta_dir
from geo_activity_playground.core.paths import activity_extracted_time_series_dir
from geo_activity_playground.core.tasks import stored_object
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.importers.activity_parsers import ActivityParseError
from geo_activity_playground.importers.activity_parsers import read_activity

logger = logging.getLogger(__name__)

ACTIVITY_DIR = pathlib.Path("Activities")


def import_from_directory(
    metadata_extraction_regexes: list[str], num_processes: Optional[int], config: Config
) -> None:

    activity_paths = [
        path
        for path in ACTIVITY_DIR.rglob("*.*")
        if path.is_file()
        and path.suffixes
        and not path.stem.startswith(".")
        and not path.suffix in config.ignore_suffixes
    ]
    work_tracker = WorkTracker(activity_extracted_dir() / "work-tracker-extract.pickle")
    new_activity_paths = work_tracker.filter(activity_paths)

    with stored_object(
        activity_extracted_dir() / "file-hashes.pickle", {}
    ) as file_hashes:
        for path in tqdm(new_activity_paths, desc="Detect deleted activities"):
            file_hashes[path] = get_file_hash(path)

        deleted_files = set(file_hashes.keys()) - set(activity_paths)
        deleted_hashes = [file_hashes[path] for path in deleted_files]
        for deleted_hash in deleted_hashes:
            activity_extracted_meta_path = (
                activity_extracted_meta_dir() / f"{deleted_hash}.pickle"
            )
            activity_extracted_time_series_path = (
                activity_extracted_time_series_dir() / f"{deleted_hash}.parquet"
            )
            logger.warning(f"Deleting {activity_extracted_meta_path}")
            logger.warning(f"Deleting {activity_extracted_time_series_path}")
            activity_extracted_meta_path.unlink(missing_ok=True)
            activity_extracted_time_series_path.unlink(missing_ok=True)
        for deleted_file in deleted_files:
            logger.warning(f"Deleting {deleted_file}")
            del file_hashes[deleted_file]
            work_tracker.discard(deleted_file)

    if num_processes == 1:
        paths_with_errors = []
        for path in tqdm(new_activity_paths, desc="Parse activity metadata (serially)"):
            errors = _cache_single_file(path)
            if errors:
                paths_with_errors.append(errors)
    else:
        with multiprocessing.Pool(num_processes) as pool:
            paths_with_errors = tqdm(
                pool.imap(_cache_single_file, new_activity_paths),
                desc="Parse activity metadata (concurrently)",
                total=len(new_activity_paths),
            )
            paths_with_errors = [error for error in paths_with_errors if error]

    for path in tqdm(new_activity_paths, desc="Collate activity metadata"):
        activity_id = get_file_hash(path)
        file_metadata_path = activity_extracted_meta_dir() / f"{activity_id}.pickle"
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
        with open(file_metadata_path, "wb") as f:
            pickle.dump(activity_meta, f)

    if paths_with_errors:
        logger.warning(
            "There were errors while parsing some of the files. These were skipped and tried again next time."
        )
        for path, error in paths_with_errors:
            logger.error(f"{path}: {error}")

    work_tracker.close()


def _cache_single_file(path: pathlib.Path) -> Optional[tuple[pathlib.Path, str]]:
    activity_id = get_file_hash(path)
    timeseries_path = activity_extracted_time_series_dir() / f"{activity_id}.parquet"
    file_metadata_path = activity_extracted_meta_dir() / f"{activity_id}.pickle"

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
            return None

        timeseries.to_parquet(timeseries_path)
        with open(file_metadata_path, "wb") as f:
            pickle.dump(activity_meta_from_file, f)
    return None


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
