import datetime
import logging
import pickle
from typing import Optional

import numpy as np
import pandas as pd
import sqlalchemy
from tqdm import tqdm

from .config import Config
from .coordinates import get_distance
from .datamodel import Activity
from .datamodel import ActivityMeta
from .datamodel import DB
from .datamodel import get_or_make_equipment
from .datamodel import get_or_make_kind
from .missing_values import some
from .paths import activity_extracted_meta_dir
from .paths import activity_extracted_time_series_dir
from .paths import time_series_dir
from .tiles import compute_tile_float
from .time_conversion import convert_to_datetime_ns

logger = logging.getLogger(__name__)


def populate_database_from_extracted(config: Config) -> None:
    available_ids = {
        int(path.stem) for path in activity_extracted_meta_dir().glob("*.pickle")
    }
    present_ids = {
        int(elem)
        for elem in DB.session.scalars(sqlalchemy.select(Activity.upstream_id)).all()
        if elem
    }
    new_ids = available_ids - present_ids

    for upstream_id in tqdm(new_ids, desc="Importing new activities into database"):
        extracted_metadata_path = (
            activity_extracted_meta_dir() / f"{upstream_id}.pickle"
        )
        with open(extracted_metadata_path, "rb") as f:
            extracted_metadata: ActivityMeta = pickle.load(f)

        extracted_time_series_path = (
            activity_extracted_time_series_dir() / f"{upstream_id}.parquet"
        )
        time_series = pd.read_parquet(extracted_time_series_path)

        # Skip activities that don't have geo information attached to them. This shouldn't happen, though.
        if "latitude" not in time_series.columns:
            logger.warning(
                f"Activity {upstream_id} doesn't have latitude/longitude information. Ignoring this one."
            )
            continue

        time_series = _embellish_single_time_series(
            time_series,
            extracted_metadata.get("start", None),
            config.time_diff_threshold_seconds,
        )

        kind_name = extracted_metadata.get("kind", None)
        if kind_name:
            # Rename kinds if needed.
            if kind_name in config.kind_renames:
                kind_name = config.kind_renames[kind_name]
            kind = get_or_make_kind(kind_name, config)
        else:
            kind = None

        equipment_name = extracted_metadata.get("equipment", None)
        if equipment_name:
            equipment = get_or_make_equipment(equipment_name, config)
        elif kind:
            equipment = kind.default_equipment
        else:
            equipment = None

        activity = Activity(
            name=extracted_metadata.get("name", "Name Placeholder"),
            distance_km=0,
            equipment=equipment,
            kind=kind,
            calories=some(extracted_metadata.get("calories", None)),
            elevation_gain=some(extracted_metadata.get("elevation_gain", None)),
            steps=some(extracted_metadata.get("steps", None)),
            path=extracted_metadata.get("path", None),
            upstream_id=upstream_id,
        )

        update_via_time_series(activity, time_series)

        DB.session.add(activity)
        try:
            DB.session.commit()
        except sqlalchemy.exc.StatementError:
            logger.error(
                f"Could not insert the following activity into the database: {vars(activity)=}"
            )
            raise

        enriched_time_series_path = time_series_dir() / f"{activity.id}.parquet"
        time_series.to_parquet(enriched_time_series_path)


def update_via_time_series(
    activity: Activity, time_series: pd.DataFrame
) -> ActivityMeta:
    activity.start = some(time_series["time"].iloc[0])
    activity.elapsed_time = some(
        time_series["time"].iloc[-1] - time_series["time"].iloc[0]
    )
    activity.distance_km = (
        time_series["distance_km"].iloc[-1] - time_series["distance_km"].iloc[0]
    )
    if "calories" in time_series.columns:
        activity.calories = (
            time_series["calories"].iloc[-1] - time_series["calories"].iloc[0]
        )
    activity.moving_time = _compute_moving_time(time_series)

    activity.start_latitude = time_series["latitude"].iloc[0]
    activity.end_latitude = time_series["latitude"].iloc[-1]
    activity.start_longitude = time_series["longitude"].iloc[0]
    activity.end_longitude = time_series["longitude"].iloc[-1]
    if "elevation_gain_cum" in time_series.columns:
        elevation_gain_cum = time_series["elevation_gain_cum"].fillna(0)
        activity.elevation_gain = (
            elevation_gain_cum.iloc[-1] - elevation_gain_cum.iloc[0]
        )


def _compute_moving_time(time_series: pd.DataFrame) -> datetime.timedelta:
    def moving_time(group) -> datetime.timedelta:
        selection = group["speed"] > 1.0
        time_diff = group["time"].diff().loc[selection]
        return time_diff.sum()

    return (
        time_series.groupby("segment_id").apply(moving_time, include_groups=False).sum()
    )


def _embellish_single_time_series(
    timeseries: pd.DataFrame,
    start: Optional[datetime.datetime],
    time_diff_threshold_seconds: int,
) -> pd.DataFrame:
    if start is not None and pd.api.types.is_dtype_equal(
        timeseries["time"].dtype, "int64"
    ):
        time = timeseries["time"]
        del timeseries["time"]
        timeseries["time"] = [
            convert_to_datetime_ns(start + datetime.timedelta(seconds=t)) for t in time
        ]
    timeseries["time"] = convert_to_datetime_ns(timeseries["time"])
    assert pd.api.types.is_dtype_equal(timeseries["time"].dtype, "datetime64[ns]"), (
        timeseries["time"].dtype,
        timeseries["time"].iloc[0],
    )

    distances = get_distance(
        timeseries["latitude"].shift(1),
        timeseries["longitude"].shift(1),
        timeseries["latitude"],
        timeseries["longitude"],
    ).fillna(0.0)
    if time_diff_threshold_seconds:
        time_diff = (
            timeseries["time"] - timeseries["time"].shift(1)
        ).dt.total_seconds()
        jump_indices = time_diff >= time_diff_threshold_seconds
        distances.loc[jump_indices] = 0.0

    if "distance_km" not in timeseries.columns:
        timeseries["distance_km"] = pd.Series(np.cumsum(distances)) / 1000

    if "speed" not in timeseries.columns:
        timeseries["speed"] = (
            timeseries["distance_km"].diff()
            / (timeseries["time"].diff().dt.total_seconds() + 1e-3)
            * 3600
        )

    potential_jumps = (timeseries["speed"] > 40) & (timeseries["speed"].diff() > 10)
    if np.any(potential_jumps):
        timeseries = timeseries.loc[~potential_jumps].copy()

    if "segment_id" not in timeseries.columns:
        if time_diff_threshold_seconds:
            timeseries["segment_id"] = np.cumsum(jump_indices)
        else:
            timeseries["segment_id"] = 0

    if "x" not in timeseries.columns:
        x, y = compute_tile_float(timeseries["latitude"], timeseries["longitude"], 0)
        timeseries["x"] = x
        timeseries["y"] = y

    if "altitude" in timeseries.columns:
        timeseries.rename(columns={"altitude": "elevation"}, inplace=True)
    if "elevation" in timeseries.columns:
        elevation_diff = timeseries["elevation"].diff()
        elevation_diff = elevation_diff.ewm(span=5, min_periods=5).mean()
        elevation_diff.loc[elevation_diff.abs() > 30] = 0
        elevation_diff.loc[elevation_diff < 0] = 0
        timeseries["elevation_gain_cum"] = elevation_diff.cumsum()

    return timeseries
