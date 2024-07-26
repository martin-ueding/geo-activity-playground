import datetime
import functools
import logging
import pathlib
from typing import Iterator
from typing import Optional
from typing import TypedDict

import geojson
import matplotlib
import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.config import get_config
from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.paths import activities_path
from geo_activity_playground.core.paths import activity_timeseries_path
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.time_conversion import convert_to_datetime_ns

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
    name: str
    path: str
    start_latitude: float
    start_longitude: float
    start: datetime.datetime
    steps: int


class ActivityRepository:
    def __init__(self) -> None:
        if activities_path().exists():
            self.meta = pd.read_parquet(activities_path())
            self.meta.index = self.meta["id"]
            self.meta.index.name = "index"
        else:
            self.meta = pd.DataFrame()

        self._loose_activities: list[ActivityMeta] = []
        self._loose_activity_ids: set[int] = set()

    def __len__(self) -> int:
        return len(self.meta)

    def add_activity(self, activity_meta: ActivityMeta) -> None:
        _extend_metadata_from_timeseries(activity_meta)
        if activity_meta["id"] in self._loose_activity_ids:
            logger.error(f"Activity with the same file already exists. New activity:")
            print(activity_meta)
            print("Existing activity:")
            print(
                [
                    activity
                    for activity in self._loose_activities
                    if activity["id"] == activity_meta["id"]
                ]
            )
            raise ValueError("Activity with the same file already exists.")
        self._loose_activities.append(activity_meta)
        self._loose_activity_ids.add(activity_meta["id"])

    def commit(self) -> None:
        if self._loose_activities:
            logger.debug(
                f"Adding {len(self._loose_activities)} activities to the repository …"
            )
            new_df = pd.DataFrame(self._loose_activities)
            if len(self.meta):
                new_ids_set = set(new_df["id"])
                is_kept = [
                    activity_id not in new_ids_set for activity_id in self.meta["id"]
                ]
                old_df = self.meta.loc[is_kept]
            else:
                old_df = self.meta
            self.meta = pd.concat([old_df, new_df])
            assert pd.api.types.is_dtype_equal(
                self.meta["start"].dtype, "datetime64[ns]"
            ), (self.meta["start"].dtype, self.meta["start"].iloc[0])
            self.save()
            self._loose_activities = []

    def save(self) -> None:
        self.meta.index = self.meta["id"]
        self.meta.index.name = "index"
        self.meta.sort_values("start", inplace=True)
        self.meta.to_parquet(activities_path())

    def has_activity(self, activity_id: int) -> bool:
        if len(self.meta):
            if activity_id in self.meta["id"]:
                return True

        for activity_meta in self._loose_activities:
            if activity_meta["id"] == activity_id:
                return True

        return False

    def last_activity_date(self) -> Optional[datetime.datetime]:
        if len(self.meta):
            return self.meta.iloc[-1]["start"]
        else:
            return None

    def get_activity_ids(self, only_achievements: bool = False) -> set[int]:
        if only_achievements:
            return set(self.meta.loc[self.meta["consider_for_achievements"]].index)
        else:
            return set(self.meta.index)

    def iter_activities(self, new_to_old=True, dropna=False) -> Iterator[ActivityMeta]:
        direction = -1 if new_to_old else 1
        for index, row in self.meta[::direction].iterrows():
            if not dropna or not pd.isna(row["start"]):
                yield row

    @functools.lru_cache()
    def get_activity_by_id(self, id: int) -> ActivityMeta:
        activity = self.meta.loc[id]
        assert isinstance(activity["name"], str), activity["name"]
        return activity

    @functools.lru_cache(maxsize=3000)
    def get_time_series(self, id: int) -> pd.DataFrame:
        path = activity_timeseries_path(id)
        try:
            df = pd.read_parquet(path)
        except OSError as e:
            logger.error(f"Error while reading {path}, deleting cache file …")
            path.unlink(missing_ok=True)
            raise

        return df


def embellish_time_series(repository: ActivityRepository) -> None:
    work_tracker = WorkTracker("embellish-time-series")
    activities_to_process = work_tracker.filter(repository.get_activity_ids())
    for activity_id in tqdm(activities_to_process, desc="Embellish time series data"):
        path = activity_timeseries_path(activity_id)
        df = pd.read_parquet(path)
        df.name = id
        df, changed = embellish_single_time_series(
            df, repository.get_activity_by_id(activity_id)["start"]
        )
        if changed:
            df.to_parquet(path)
        work_tracker.mark_done(activity_id)
    work_tracker.close()


def embellish_single_time_series(
    timeseries: pd.DataFrame, start: Optional[datetime.datetime] = None
) -> bool:
    changed = False

    if start is not None and pd.api.types.is_dtype_equal(
        timeseries["time"].dtype, "int64"
    ):
        time = timeseries["time"]
        del timeseries["time"]
        timeseries["time"] = [
            convert_to_datetime_ns(start + datetime.timedelta(seconds=t)) for t in time
        ]
        changed = True
    assert pd.api.types.is_dtype_equal(timeseries["time"].dtype, "datetime64[ns]")

    distances = get_distance(
        timeseries["latitude"].shift(1),
        timeseries["longitude"].shift(1),
        timeseries["latitude"],
        timeseries["longitude"],
    ).fillna(0.0)
    time_diff_threshold_seconds = 30
    time_diff = (timeseries["time"] - timeseries["time"].shift(1)).dt.total_seconds()
    jump_indices = (time_diff >= time_diff_threshold_seconds) & (distances > 100)
    distances.loc[jump_indices] = 0.0

    if not "distance_km" in timeseries.columns:
        timeseries["distance_km"] = pd.Series(np.cumsum(distances)) / 1000
        changed = True

    if "speed" not in timeseries.columns:
        timeseries["speed"] = (
            timeseries["distance_km"].diff()
            / (timeseries["time"].diff().dt.total_seconds() + 1e-3)
            * 3600
        )
        changed = True

    potential_jumps = (timeseries["speed"] > 40) & (timeseries["speed"].diff() > 10)
    if np.any(potential_jumps):
        timeseries = timeseries.loc[~potential_jumps].copy()
        changed = True

    if "segment_id" not in timeseries.columns:
        timeseries["segment_id"] = np.cumsum(jump_indices)
        changed = True

    if "x" not in timeseries.columns:
        x, y = compute_tile_float(timeseries["latitude"], timeseries["longitude"], 0)
        timeseries["x"] = x
        timeseries["y"] = y
        changed = True

    return timeseries, changed


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


def make_speed_color_bar(time_series: pd.DataFrame) -> dict[str, str]:
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


def _extend_metadata_from_timeseries(metadata: ActivityMeta) -> None:
    timeseries = pd.read_parquet(
        pathlib.Path("Cache/Activity Timeseries") / f"{metadata['id']}.parquet"
    )

    metadata["start_latitude"] = timeseries["latitude"].iloc[0]
    metadata["end_latitude"] = timeseries["latitude"].iloc[-1]
    metadata["start_longitude"] = timeseries["longitude"].iloc[0]
    metadata["end_longitude"] = timeseries["longitude"].iloc[-1]
