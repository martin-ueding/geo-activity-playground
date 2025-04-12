import datetime
import functools
import json
import logging
import pickle
from collections.abc import Callable
from typing import Any
from typing import Iterator
from typing import Optional
from typing import TypedDict

import geojson
import matplotlib
import numpy as np
import pandas as pd
import sqlalchemy.orm
from tqdm import tqdm

from geo_activity_playground.core.datamodel import Activity
from geo_activity_playground.core.datamodel import get_or_make_equipment
from geo_activity_playground.core.datamodel import get_or_make_kind
from geo_activity_playground.core.paths import activities_file
from geo_activity_playground.core.paths import activity_enriched_meta_dir
from geo_activity_playground.core.paths import activity_enriched_time_series_dir
from geo_activity_playground.core.paths import activity_meta_override_dir

logger = logging.getLogger(__name__)


class ActivityMeta(TypedDict):
    average_speed_elapsed_kmh: float
    average_speed_moving_kmh: float
    calories: float
    commute: bool
    consider_for_achievements: bool
    distance_km: float
    elapsed_time: datetime.timedelta
    elevation_gain: float
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


def build_activity_meta(database: sqlalchemy.orm.Session) -> None:
    available_ids = {
        int(path.stem) for path in activity_enriched_meta_dir().glob("*.pickle")
    }

    for legacy_id in available_ids:
        result = database.scalars(
            sqlalchemy.select(Activity).where(Activity.id == legacy_id)
        ).all()
        if result:
            continue
        with open(activity_enriched_meta_dir() / f"{legacy_id}.pickle", "rb") as f:
            data: ActivityMeta = pickle.load(f)
        override_file = activity_meta_override_dir() / f"{legacy_id}.json"
        if override_file.exists():
            with open(override_file) as f:
                data.update(json.load(f))

        del data["consider_for_achievements"]
        del data["commute"]

        if data["kind"] == "Unknown":
            data["kind"] = None
        else:
            data["kind"] = get_or_make_kind(data["kind"], database)
        if data["equipment"] == "Unknown":
            data["equipment"] = None
        else:
            data["equipment"] = get_or_make_equipment(data["equipment"], database)

        print(data)
        activity = Activity(**data)
        database.add(activity)
        database.commit()


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
        self.meta.to_parquet(activities_file())


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


def inter_quartile_range(values):
    return np.quantile(values, 0.75) - np.quantile(values, 0.25)


def make_geojson_color_line(time_series: pd.DataFrame) -> str:
    low, high, clamp_speed = _make_speed_clamp(time_series["speed"])
    cmap = matplotlib.colormaps["viridis"]
    features = [
        geojson.Feature(
            geometry=geojson.LineString(
                coordinates=[
                    [row["longitude"], row["latitude"]],
                    [next_row["longitude"], next_row["latitude"]],
                ]
            ),
            properties={
                "speed": next_row["speed"] if np.isfinite(next_row["speed"]) else 0.0,
                "color": matplotlib.colors.to_hex(cmap(clamp_speed(next_row["speed"]))),
            },
        )
        for _, group in time_series.groupby("segment_id")
        for (_, row), (_, next_row) in zip(group.iterrows(), group.iloc[1:].iterrows())
    ]
    feature_collection = geojson.FeatureCollection(features)
    return geojson.dumps(feature_collection)


def make_speed_color_bar(time_series: pd.DataFrame) -> dict[str, Any]:
    low, high, clamp_speed = _make_speed_clamp(time_series["speed"])
    cmap = matplotlib.colormaps["viridis"]
    colors = [
        (f"{speed:.1f}", matplotlib.colors.to_hex(cmap(clamp_speed(speed))))
        for speed in np.linspace(low, high, 10)
    ]
    return {"low": low, "high": high, "colors": colors}


def _make_speed_clamp(speeds: pd.Series) -> tuple[float, float, Callable]:
    speed_without_na = speeds.dropna()
    low = min(speed_without_na)
    high = min(
        max(speed_without_na),
        np.median(speed_without_na) + 1.5 * inter_quartile_range(speed_without_na),
    )
    return low, high, lambda speed: min(max((speed - low) / (high - low), 0.0), 1.0)
