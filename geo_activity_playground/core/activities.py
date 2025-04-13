import datetime
import functools
import json
import logging
import pathlib
import pickle
import shutil
from collections.abc import Callable
from typing import Any
from typing import Iterator
from typing import Optional

import geojson
import matplotlib
import numpy as np
import pandas as pd
import sqlalchemy.orm
from tqdm import tqdm

from geo_activity_playground.core.datamodel import Activity
from geo_activity_playground.core.datamodel import ActivityMeta
from geo_activity_playground.core.datamodel import Equipment
from geo_activity_playground.core.datamodel import get_or_make_equipment
from geo_activity_playground.core.datamodel import get_or_make_kind
from geo_activity_playground.core.datamodel import Kind
from geo_activity_playground.core.paths import activity_enriched_meta_dir
from geo_activity_playground.core.paths import activity_enriched_time_series_dir
from geo_activity_playground.core.paths import activity_meta_override_dir
from geo_activity_playground.core.paths import time_series_dir

logger = logging.getLogger(__name__)


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

    for legacy_id in tqdm(available_ids, desc="Importing activities into database"):
        pickle_path = activity_enriched_meta_dir() / f"{legacy_id}.pickle"
        result = database.scalar(
            sqlalchemy.select(Activity).where(Activity.path == str(pickle_path))
        )
        if result is not None:
            continue
        with open(pickle_path, "rb") as f:
            data: ActivityMeta = pickle.load(f)
        override_file = activity_meta_override_dir() / f"{legacy_id}.json"
        if override_file.exists():
            with open(override_file) as f:
                data.update(json.load(f))

        del data["consider_for_achievements"]
        del data["commute"]
        del data["id"]
        data["path"] = str(pickle_path)

        if data["kind"] == "Unknown":
            data["kind"] = None
        else:
            data["kind"] = get_or_make_kind(data["kind"], database)
        if data["equipment"] == "Unknown":
            data["equipment"] = None
        else:
            data["equipment"] = get_or_make_equipment(data["equipment"], database)

        activity = Activity(**data)
        database.add(activity)
        database.commit()

        enriched_time_series_path = (
            activity_enriched_time_series_dir() / f"{legacy_id}.parquet"
        )
        shutil.copy(
            enriched_time_series_path, time_series_dir() / f"{activity.id}.parquet"
        )


class ActivityRepository:
    def __init__(self, db_session: sqlalchemy.orm.Session) -> None:
        self._db_session = db_session

    def __len__(self) -> int:
        return len(self.get_activity_ids())

    def has_activity(self, activity_id: int) -> bool:
        return bool(
            self._db_session.scalars(
                sqlalchemy.query(Activity).where(Activity.id == activity_id)
            ).all()
        )

    def last_activity_date(self) -> Optional[datetime.datetime]:
        result = self._db_session.scalars(
            sqlalchemy.select(Activity).order_by(Activity.start)
        ).all()
        if result:
            return result[-1].start
        else:
            return None

    def get_activity_ids(self, only_achievements: bool = False) -> list[int]:
        query = sqlalchemy.select(Activity.id)
        if only_achievements:
            query = query.where(Kind.consider_for_achievements)
        result = self._db_session.scalars(query).all()
        return result

    def iter_activities(self, new_to_old=True, drop_na=False) -> list[Activity]:
        query = sqlalchemy.select(Activity)
        if drop_na:
            query = query.where(Activity.start.is_not(None))
        result = self._db_session.scalars(query.order_by(Activity.start)).all()
        direction = -1 if new_to_old else 1
        return result[::direction]

    def get_activity_by_id(self, id: int) -> Activity:
        activity = self._db_session.scalar(
            sqlalchemy.select(Activity).where(Activity.id == int(id))
        )
        if activity is None:
            raise ValueError(f"Cannot find activity {id} in database.")
        return activity

    @functools.lru_cache(maxsize=3000)
    def get_time_series(self, id: int) -> pd.DataFrame:
        return self.get_activity_by_id(id).timeseries

    @property
    def meta(self) -> pd.DataFrame:
        activities = self.iter_activities(new_to_old=False, drop_na=True)
        df = pd.DataFrame([activity.to_dict() for activity in activities])
        df["year"] = [start.year for start in df["start"]]
        df["month"] = [start.month for start in df["start"]]
        df["day"] = [start.day for start in df["start"]]
        df["week"] = [start.isocalendar().week for start in df["start"]]
        df["iso_year"] = [start.isocalendar().year for start in df["start"]]
        df["hours"] = [
            elapsed_time.total_seconds() / 3600 for elapsed_time in df["elapsed_time"]
        ]
        df.index = df["id"]
        return df


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
