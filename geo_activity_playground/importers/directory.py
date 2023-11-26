import hashlib
import logging
import pathlib
import traceback

import numpy as np
import pandas as pd

from geo_activity_playground.core.activity_parsers import ActivityParseError
from geo_activity_playground.core.activity_parsers import read_activity
from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.tasks import work_tracker

logger = logging.getLogger(__name__)


def import_from_directory() -> None:
    meta_file = pathlib.Path("Cache") / "activities.parquet"
    if meta_file.exists():
        logger.info("Loading metadata file …")
        meta = pd.read_parquet(meta_file)
    else:
        logger.info("Didn't find a metadata file.")
        meta = None

    paths_with_errors = []

    with work_tracker(pathlib.Path("Cache/parsed_activities.json")) as already_parsed:
        activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
        activity_stream_dir.mkdir(exist_ok=True, parents=True)
        new_rows: list[dict] = []
        for path in pathlib.Path("Activities").rglob("*.*"):
            id = int(hashlib.sha3_224(str(path).encode()).hexdigest(), 16) % 2**62
            if id in already_parsed:
                continue

            logger.info(f"Parsing activity file {path} …")
            try:
                timeseries = read_activity(path)
            except ActivityParseError as e:
                logger.error(f"Error while parsing file {path}:")
                traceback.print_exc()
                paths_with_errors.append((path, str(e)))
                continue
            else:
                already_parsed.add(id)

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

            timeseries_path = activity_stream_dir / f"{id}.parquet"
            timeseries.to_parquet(timeseries_path)

            row = {
                "id": id,
                "commute": None,
                "distance": distance,
                "name": path.stem,
                "kind": None,
                "start": timeseries["time"].iloc[0],
                "elapsed_time": timeseries["time"].iloc[-1]
                - timeseries["time"].iloc[0],
                "equipment": None,
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
    merged: pd.DataFrame = pd.concat([meta, new_df])
    merged.sort_values("start", inplace=True)
    meta_file.parent.mkdir(exist_ok=True, parents=True)
    merged.to_parquet(meta_file)
