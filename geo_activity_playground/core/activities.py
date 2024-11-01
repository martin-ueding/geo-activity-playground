import datetime
import functools
import json
import logging
import pickle
from typing import Any
from typing import Iterator
from typing import Optional
from typing import TypedDict

import geojson
import matplotlib
import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.paths import activities_file
from geo_activity_playground.core.paths import activity_enriched_meta_dir
from geo_activity_playground.core.paths import activity_enriched_time_series_dir
from geo_activity_playground.core.paths import activity_meta_override_dir

logger = logging.getLogger(__name__)


class ActivityMeta(TypedDict):
    calories: float
    commute: bool
    consider_for_achievements: bool
    distance_km: float
    elapsed_time: datetime.timedelta
    end_latitude: float
    end_longitude: float
    equipment: str
    id: int
    kind: str
    moving_time: datetime.timedelta
    name: str
    path: str
    start_latitude: float
    start_longitude: float
    start: np.datetime64
    steps: int


def make_activity_meta() -> ActivityMeta:
    return ActivityMeta(
        calories=None,
        commute=False,
        consider_for_achievements=True,
        equipment="Unknown",
        kind="Unknown",
        steps=None,
    )


def build_activity_meta() -> None:
    if activities_file().exists():
        meta = pd.read_parquet(activities_file())
        present_ids = set(meta["id"])
    else:
        meta = pd.DataFrame(columns=["id"])
        present_ids = set()

    available_ids = {
        int(path.stem) for path in activity_enriched_meta_dir().glob("*.pickle")
    }
    new_ids = available_ids - present_ids
    deleted_ids = present_ids - available_ids

    # Remove updated activities and read these again.
    if activities_file().exists():
        meta_mtime = activities_file().stat().st_mtime
        updated_ids = {
            int(path.stem)
            for path in activity_enriched_meta_dir().glob("*.pickle")
            if path.stat().st_mtime > meta_mtime
        }
        new_ids.update(updated_ids)
        deleted_ids.update(updated_ids & present_ids)

    if deleted_ids:
        logger.debug(f"Removing activities {deleted_ids} from repository.")
        meta.drop(sorted(deleted_ids), axis="index", inplace=True)

    rows = []
    for new_id in tqdm(new_ids, desc="Register new activities"):
        with open(activity_enriched_meta_dir() / f"{new_id}.pickle", "rb") as f:
            data = pickle.load(f)
        override_file = activity_meta_override_dir() / f"{new_id}.json"
        if override_file.exists():
            with open(override_file) as f:
                data.update(json.load(f))
        rows.append(data)

    if rows:
        new_shard = pd.DataFrame(rows)
        new_shard.index = new_shard["id"]
        new_shard.index.name = "index"
        if len(meta):
            meta = pd.concat([meta, new_shard])
        else:
            meta = new_shard

    if len(meta):
        assert pd.api.types.is_dtype_equal(meta["start"].dtype, "datetime64[ns]"), (
            meta["start"].dtype,
            meta["start"].iloc[0],
        )

        meta.sort_values("start", inplace=True)

    meta.to_parquet(activities_file())


class ActivityRepository:
    def __init__(self) -> None:
        self.meta = pd.DataFrame()

    def __len__(self) -> int:
        return len(self.meta)

    def reload(self) -> None:
        self.meta = pd.read_parquet(activities_file())

    def has_activity(self, activity_id: int) -> bool:
        if len(self.meta):
            if activity_id in self.meta["id"]:
                return True

        return False

    def last_activity_date(self) -> Optional[datetime.datetime]:
        if len(self.meta):
            return self.meta.iloc[-1]["start"]
        else:
            return None

    def get_activity_ids(self, only_achievements: bool = False) -> list[int]:
        if only_achievements:
            return list(self.meta.loc[self.meta["consider_for_achievements"]].index)
        else:
            return list(self.meta.index)

    def iter_activities(self, new_to_old=True, dropna=False) -> Iterator[ActivityMeta]:
        direction = -1 if new_to_old else 1
        for index, row in self.meta[::direction].iterrows():
            if not dropna or not pd.isna(row["start"]):
                yield row

    def get_activity_by_id(self, id: int) -> ActivityMeta:
        activity = self.meta.loc[id]
        assert isinstance(activity["name"], str), activity["name"]
        return activity

    @functools.lru_cache(maxsize=3000)
    def get_time_series(self, id: int) -> pd.DataFrame:
        path = activity_enriched_time_series_dir() / f"{id}.parquet"
        try:
            df = pd.read_parquet(path)
        except OSError as e:
            logger.error(f"Error while reading {path}, deleting cache file …")
            path.unlink(missing_ok=True)
            raise

        return df

    def save(self) -> None:
        self._meta.to_parquet(activities_file())


def make_geojson_from_time_series(time_series: pd.DataFrame) -> str:
    fc = geojson.FeatureCollection(
        features=[
            geojson.LineString(
                [(lon, lat) for lat, lon in zip(group["latitude"], group["longitude"])]
            )
            for _, group in time_series.groupby("segment_id")
        ]
    )
    return geojson.dumps(fc)


def make_geojson_color_line(time_series: pd.DataFrame) -> str:
    speed_without_na = time_series["speed"].dropna()
    low = min(speed_without_na)
    high = max(speed_without_na)
    clamp_speed = lambda speed: min(max((speed - low) / (high - low), 0.0), 1.0)

    cmap = matplotlib.colormaps["viridis"]
    features = [
        geojson.Feature(
            geometry=geojson.LineString(
                coordinates=[
                    [row["longitude"], row["latitude"]],
                    [next["longitude"], next["latitude"]],
                ]
            ),
            properties={
                "speed": next["speed"] if np.isfinite(next["speed"]) else 0.0,
                "color": matplotlib.colors.to_hex(cmap(clamp_speed(next["speed"]))),
            },
        )
        for _, group in time_series.groupby("segment_id")
        for (_, row), (_, next) in zip(group.iterrows(), group.iloc[1:].iterrows())
    ]
    feature_collection = geojson.FeatureCollection(features)
    return geojson.dumps(feature_collection)


def make_speed_color_bar(time_series: pd.DataFrame) -> dict[str, Any]:
    speed_without_na = time_series["speed"].dropna()
    low = min(speed_without_na)
    high = max(speed_without_na)
    cmap = matplotlib.colormaps["viridis"]
    clamp_speed = lambda speed: min(max((speed - low) / (high - low), 0.0), 1.0)
    colors = [
        (f"{speed:.1f}", matplotlib.colors.to_hex(cmap(clamp_speed(speed))))
        for speed in np.linspace(low, high, 10)
    ]
    return {"low": low, "high": high, "colors": colors}
