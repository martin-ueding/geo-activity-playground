import hashlib
import logging
import pathlib
import sys
import traceback

import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activity_parsers import ActivityParseError
from geo_activity_playground.core.activity_parsers import read_activity
from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.tasks import WorkTracker

logger = logging.getLogger(__name__)


def import_from_directory() -> None:
    meta_file = pathlib.Path("Cache") / "activities.parquet"
    if meta_file.exists():
        meta = pd.read_parquet(meta_file)
    else:
        meta = None

    paths_with_errors = []
    work_tracker = WorkTracker("parse-activity-files")

    activity_paths = {
        int(hashlib.sha3_224(str(path).encode()).hexdigest(), 16) % 2**62: path
        for path in pathlib.Path("Activities").rglob("*.*")
    }
    activities_ids_to_parse = work_tracker.filter(activity_paths.keys())

    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    activity_stream_dir.mkdir(exist_ok=True, parents=True)
    new_rows: list[dict] = []
    for activity_id in tqdm(activities_ids_to_parse, desc="Parse activity files"):
        path = activity_paths[activity_id]
        try:
            timeseries = read_activity(path)
        except ActivityParseError as e:
            logger.error(f"Error while parsing file {path}:")
            traceback.print_exc()
            paths_with_errors.append((path, str(e)))
            continue

        work_tracker.mark_done(activity_id)

        if len(timeseries) == 0:
            continue

        timeseries["time"] = timeseries["time"].dt.tz_localize("UTC")

        if "distance" not in timeseries.columns:
            distances = [0] + [
                get_distance(lat_1, lon_1, lat_2, lon_2)
                for lat_1, lon_1, lat_2, lon_2 in zip(
                    timeseries["latitude"],
                    timeseries["longitude"],
                    timeseries["latitude"].iloc[1:],
                    timeseries["longitude"].iloc[1:],
                )
            ]
            timeseries["distance"] = pd.Series(np.cumsum(distances))
        distance = timeseries["distance"].iloc[-1]

        timeseries_path = activity_stream_dir / f"{activity_id}.parquet"
        timeseries.to_parquet(timeseries_path)

        commute = False
        if path.parts[-2] == "Commute":
            commute = True
        kind = None
        if len(path.parts) >= 3 and path.parts[1] != "Commute":
            kind = path.parts[1]
        equipment = None
        if len(path.parts) >= 4 and path.parts[2] != "Commute":
            equipment = path.parts[2]

        row = {
            "id": activity_id,
            "commute": commute,
            "distance": distance,
            "name": path.stem,
            "kind": kind,
            "start": timeseries["time"].iloc[0],
            "elapsed_time": timeseries["time"].iloc[-1] - timeseries["time"].iloc[0],
            "equipment": equipment,
            "calories": 0,
        }

        if "calories" in timeseries.columns:
            row["calories"] = timeseries["calories"].iloc[-1]

        new_rows.append(row)

    if paths_with_errors:
        logger.warning(
            "There were errors while parsing some of the files. These were skipped and tried again next time."
        )
        for path, error in paths_with_errors:
            logger.error(f"{path}: {error}")

    new_df = pd.DataFrame(new_rows)
    merged = pd.concat([meta, new_df])

    if len(merged) == 0:
        activities_dir = pathlib.Path("Activities").resolve()
        logger.error(
            f"You seemingly want to use activity files as a data source, but you have not copied any GPX/FIT/TCX/KML files."
            f"Please copy at least one such file into {activities_dir}."
        )
        sys.exit(1)

    merged.sort_values("start", inplace=True)
    meta_file.parent.mkdir(exist_ok=True, parents=True)
    merged.to_parquet(meta_file)
    work_tracker.close()
