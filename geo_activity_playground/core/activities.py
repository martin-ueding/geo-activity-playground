import dataclasses
import datetime
import functools
import logging
import pathlib
from typing import Iterator
from typing import Optional

import geojson
import matplotlib
import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.config import get_config
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.core.tiles import compute_tile_float


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ActivityMeta:
    calories: float
    commute: bool
    distance: float
    elapsed_time: datetime.timedelta
    equipment: str
    id: int
    kind: str
    name: str
    start: datetime.datetime

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}; {self.distance:.1f} km; {self.elapsed_time})"


class ActivityRepository:
    def __init__(self) -> None:
        self.meta = pd.read_parquet("Cache/activities.parquet")
        self.meta.index = self.meta["id"]
        self.meta.index.name = "index"
        self.meta["distance"] /= 1000
        self.meta["kind"].fillna("Unknown", inplace=True)
        self.meta["equipment"].fillna("Unknown", inplace=True)

    @property
    def activity_ids(self) -> set[int]:
        return set(self.meta["id"])

    def iter_activities(self, new_to_old=True) -> Iterator[ActivityMeta]:
        direction = -1 if new_to_old else 1
        for id, row in self.meta[::direction].iterrows():
            yield ActivityMeta(**row)

    @functools.lru_cache()
    def get_activity_by_id(self, id: int) -> ActivityMeta:
        return ActivityMeta(**self.meta.loc[id])

    @functools.lru_cache(maxsize=3000)
    def get_time_series(self, id: int) -> pd.DataFrame:
        path = pathlib.Path(f"Cache/Activity Timeseries/{id}.parquet")
        try:
            df = pd.read_parquet(path)
        except OSError as e:
            logger.error(f"Error while reading {path}, deleting cache file …")
            path.unlink(missing_ok=True)
            raise
        df.name = id
        changed = False
        if pd.api.types.is_dtype_equal(df["time"].dtype, "int64"):
            start = self.get_activity_by_id(id).start
            time = df["time"]
            del df["time"]
            df["time"] = [start + datetime.timedelta(seconds=t) for t in time]
            changed = True
        assert pd.api.types.is_dtype_equal(df["time"].dtype, "datetime64[ns, UTC]")

        if "distance" in df.columns:
            if "distance/km" not in df.columns:
                df["distance/km"] = df["distance"] / 1000
                changed = True

            if "speed" not in df.columns:
                df["speed"] = (
                    df["distance"].diff()
                    / (df["time"].diff().dt.total_seconds() + 1e-3)
                    * 3.6
                )
                changed = True

        if "latitude" in df.columns and "x" not in df.columns:
            x, y = compute_tile_float(df["latitude"], df["longitude"], 0)
            df["x"] = x
            df["y"] = y
            changed = True

        if "segment_id" not in df.columns:
            time_diff = (df["time"] - df["time"].shift(1)).dt.total_seconds()
            jump_indices = time_diff >= 30
            df["segment_id"] = np.cumsum(jump_indices)
            changed = True

        if changed:
            logger.info(f"Updating activity time series for {id = } …")
            df.to_parquet(path)

        return df


def embellish_time_series(repository: ActivityRepository) -> None:
    work_tracker = WorkTracker("embellish-time-series")
    activities_to_process = work_tracker.filter(repository.activity_ids)
    for activity_id in tqdm(activities_to_process, desc="Embellish time series data"):
        path = pathlib.Path(f"Cache/Activity Timeseries/{activity_id}.parquet")
        df = pd.read_parquet(path)
        df.name = id
        changed = False
        if pd.api.types.is_dtype_equal(df["time"].dtype, "int64"):
            start = repository.get_activity_by_id(activity_id).start
            time = df["time"]
            del df["time"]
            df["time"] = [start + datetime.timedelta(seconds=t) for t in time]
            changed = True
        assert pd.api.types.is_dtype_equal(df["time"].dtype, "datetime64[ns, UTC]")

        if "distance" in df.columns:
            if "distance/km" not in df.columns:
                df["distance/km"] = df["distance"] / 1000
                changed = True

            if "speed" not in df.columns:
                df["speed"] = (
                    df["distance"].diff()
                    / (df["time"].diff().dt.total_seconds() + 1e-3)
                    * 3.6
                )
                changed = True

        if "x" not in df.columns:
            x, y = compute_tile_float(df["latitude"], df["longitude"], 0)
            df["x"] = x
            df["y"] = y
            changed = True

        if "segment_id" not in df.columns:
            time_diff = (df["time"] - df["time"].shift(1)).dt.total_seconds()
            jump_indices = time_diff >= 30
            df["segment_id"] = np.cumsum(jump_indices)
            changed = True

        if changed:
            df.to_parquet(path)
        work_tracker.mark_done(activity_id)
    work_tracker.close()


def make_geojson_from_time_series(time_series: pd.DataFrame) -> str:
    line = geojson.LineString(
        [
            (lon, lat)
            for lat, lon in zip(time_series["latitude"], time_series["longitude"])
        ]
    )
    return geojson.dumps(line)


def make_geojson_color_line(time_series: pd.DataFrame) -> str:
    cmap = matplotlib.colormaps["viridis"]
    return geojson.dumps(
        geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.LineString(
                        coordinates=[
                            [row["longitude"], row["latitude"]],
                            [next["longitude"], next["latitude"]],
                        ]
                    ),
                    properties={
                        "speed": next["speed"],
                        "color": matplotlib.colors.to_hex(
                            cmap(min(next["speed"] / 35, 1.0))
                        ),
                    },
                )
                for (_, row), (_, next) in zip(
                    time_series.iterrows(), time_series.iloc[1:].iterrows()
                )
            ]
        )
    )


def extract_heart_rate_zones(time_series: pd.DataFrame) -> Optional[pd.DataFrame]:
    if "heartrate" not in time_series:
        return None
    config = get_config()
    try:
        heart_config = config["heart"]
    except KeyError:
        logger.warning(
            "Missing config entry `heart`, cannot determine heart rate zones."
        )
        return None

    birthyear = heart_config.get("birthyear", None)
    maximum = heart_config.get("maximum", None)
    resting = heart_config.get("resting", None)

    if not maximum and birthyear:
        age = time_series["time"].iloc[0].year - birthyear
        maximum = 220 - age
    if not resting:
        resting = 0
    if not maximum:
        logger.warning(
            "Missing config entry `heart.maximum` or `heart.birthyear`, cannot determine heart rate zones."
        )
        return None

    zones: pd.Series = (time_series["heartrate"] - resting) * 10 // (
        maximum - resting
    ) - 4
    zones.loc[zones < 0] = 0
    zones.loc[zones > 5] = 5
    df = pd.DataFrame({"heartzone": zones, "step": time_series["time"].diff()}).dropna()
    duration_per_zone = df.groupby("heartzone").sum()["step"].dt.total_seconds() / 60
    duration_per_zone.name = "minutes"
    for i in range(6):
        if i not in duration_per_zone:
            duration_per_zone.loc[i] = 0.0
    result = duration_per_zone.reset_index()
    return result
