import hashlib
import logging
import pathlib

import pandas as pd

from geo_activity_playground.core.activity_parsers import read_activity
from geo_activity_playground.core.coordinates import get_distance

logger = logging.getLogger(__name__)


def import_from_directory() -> None:
    meta_file = pathlib.Path("Cache") / "activities.parquet"
    if meta_file.exists():
        logger.info("Loading metadata file …")
        meta = pd.read_parquet(meta_file)
    else:
        logger.info("Didn't find a metadata file.")
        meta = None

    already_parsed = set(meta.id) if meta is not None else set()

    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    activity_stream_dir.mkdir(exist_ok=True, parents=True)
    new_rows: list[dict] = []
    for path in pathlib.Path("Activities").rglob("*.*"):
        id = int(hashlib.sha3_224(str(path).encode()).hexdigest(), 16) % 2**62
        if id in already_parsed:
            continue

        logger.info(f"Parsing activity file {path} …")
        timeseries = read_activity(path)
        timeseries_path = activity_stream_dir / f"{id}.parquet"
        print(timeseries)
        timeseries.to_parquet(timeseries_path)

        distances = [
            get_distance(lat_1, lon_1, lat_2, lon_2)
            for lat_1, lon_1, lat_2, lon_2 in zip(
                timeseries["latitude"],
                timeseries["longitude"],
                timeseries["latitude"].iloc[1:],
                timeseries["longitude"].iloc[1:],
            )
        ]

        print(len(distances))
        distance = sum(distances)

        new_rows.append(
            {
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
        )

    new_df = pd.DataFrame(new_rows)
    merged: pd.DataFrame = pd.concat([meta, new_df])
    merged.sort_values("start", inplace=True)
    meta_file.parent.mkdir(exist_ok=True, parents=True)
    merged.to_parquet(meta_file)
