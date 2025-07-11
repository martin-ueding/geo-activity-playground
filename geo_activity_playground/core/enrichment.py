import datetime
import logging
import uuid
import zoneinfo
from typing import Callable

import numpy as np
import pandas as pd

from .config import Config
from .coordinates import get_distance
from .datamodel import Activity
from .datamodel import DB
from .missing_values import some
from .tiles import compute_tile_float
from .time_conversion import get_country_timezone

logger = logging.getLogger(__name__)


def enrichment_set_timezone(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    assert (
        len(time_series) > 0
    ), f"You cannot import an activity without points. {activity=}"
    latitude, longitude = time_series[["latitude", "longitude"]].iloc[0].to_list()
    if activity.iana_timezone is None or activity.start_country is None:
        country, tz_str = get_country_timezone(latitude, longitude)
        activity.iana_timezone = tz_str
        activity.start_country = country
        return True
    else:
        return False


def enrichment_normalize_time(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    # Routes (as opposed to tracks) don't have time information. We cannot do anything with time here.
    if (
        "time" in time_series.columns
        and pd.isna(time_series["time"]).all()
        and not pd.api.types.is_datetime64_any_dtype(time_series["time"].dtype)
    ):
        time_series["time"] = pd.NaT
        return True

    changed = False
    tz_utc = zoneinfo.ZoneInfo("UTC")
    # If the time is naive, assume that it is UTC.
    if time_series["time"].dt.tz is None:
        time_series["time"] = time_series["time"].dt.tz_localize(tz_utc)
        changed = True

    if time_series["time"].dt.tz.utcoffset(None) != tz_utc.utcoffset(None):
        time_series["time"] = time_series["time"].dt.tz_convert(tz_utc)
        changed = True

    if not pd.api.types.is_dtype_equal(
        time_series["time"].dtype, "datetime64[ns, UTC]"
    ):
        time_series["time"] = time_series["time"].dt.tz_convert(tz_utc)
        changed = True

    assert pd.api.types.is_dtype_equal(
        time_series["time"].dtype, "datetime64[ns, UTC]"
    ), (
        time_series["time"].dtype,
        time_series["time"].iloc[0],
    )

    new_start = some(time_series["time"].iloc[0])
    if new_start != activity.start:
        activity.start = new_start
        changed = True

    new_elapsed_time = some(time_series["time"].iloc[-1] - time_series["time"].iloc[0])
    if new_elapsed_time != activity.elapsed_time:
        activity.elapsed_time = new_elapsed_time
        changed = True

    return changed


def enrichment_rename_altitude(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    if "altitude" in time_series.columns:
        time_series.rename(columns={"altitude": "elevation"}, inplace=True)
        return True
    else:
        return False


def enrichment_compute_tile_xy(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    if "x" not in time_series.columns:
        x, y = compute_tile_float(time_series["latitude"], time_series["longitude"], 0)
        time_series["x"] = x
        time_series["y"] = y
        return True
    else:
        return False


def enrichment_copernicus_elevation(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    from .copernicus_dem import get_elevation

    if "copernicus_elevation" not in time_series.columns:
        time_series["copernicus_elevation"] = [
            get_elevation(lat, lon)
            for lat, lon in zip(time_series["latitude"], time_series["longitude"])
        ]
        return True
    else:
        return False


def enrichment_elevation_gain(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    if (
        "elevation" in time_series.columns
        or "copernicus_elevation" in time_series.columns
    ) and "elevation_gain_cum" not in time_series.columns:
        elevation = (
            time_series["elevation"]
            if "elevation" in time_series.columns
            else time_series["copernicus_elevation"]
        )
        elevation_diff = elevation.diff()
        elevation_diff = elevation_diff.ewm(span=5, min_periods=5).mean()
        elevation_diff.loc[elevation_diff.abs() > 30] = 0
        elevation_diff.loc[elevation_diff < 0] = 0
        time_series["elevation_gain_cum"] = elevation_diff.cumsum().fillna(0)

        activity.elevation_gain = (
            time_series["elevation_gain_cum"].iloc[-1]
            - time_series["elevation_gain_cum"].iloc[0]
        )
        return True
    else:
        return False


def enrichment_add_calories(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    if activity.calories is None and "calories" in time_series.columns:
        activity.calories = (
            time_series["calories"].iloc[-1] - time_series["calories"].iloc[0]
        )
        return True
    else:
        return False


def enrichment_distance(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    changed = False

    distances = get_distance(
        time_series["latitude"].shift(1),
        time_series["longitude"].shift(1),
        time_series["latitude"],
        time_series["longitude"],
    ).fillna(0.0)

    if config.time_diff_threshold_seconds:
        time_diff = (
            time_series["time"] - time_series["time"].shift(1)
        ).dt.total_seconds()
        jump_indices = time_diff >= config.time_diff_threshold_seconds
        distances.loc[jump_indices] = 0.0

    if "distance_km" not in time_series.columns:
        time_series["distance_km"] = pd.Series(np.cumsum(distances)) / 1000
        changed = True

    if "speed" not in time_series.columns:
        time_series["speed"] = (
            time_series["distance_km"].diff()
            / (time_series["time"].diff().dt.total_seconds() + 1e-3)
            * 3600
        )
        changed = True

    potential_jumps = (time_series["speed"] > 40) & (time_series["speed"].diff() > 10)
    if np.any(potential_jumps):
        time_series.replace(time_series.loc[~potential_jumps])
        changed = True

    if "segment_id" not in time_series.columns:
        if config.time_diff_threshold_seconds:
            time_series["segment_id"] = np.cumsum(jump_indices)
        else:
            time_series["segment_id"] = 0
        changed = True

    new_distance_km = (
        time_series["distance_km"].iloc[-1] - time_series["distance_km"].iloc[0]
    )
    if new_distance_km != activity.distance_km:
        activity.distance_km = new_distance_km
        changed = True

    return changed


def enrichment_moving_time(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    def moving_time(group) -> datetime.timedelta:
        selection = group["speed"] > 1.0
        time_diff = group["time"].diff().loc[selection]
        return time_diff.sum()

    new_moving_time = (
        time_series.groupby("segment_id").apply(moving_time, include_groups=False).sum()
    )
    if new_moving_time != activity.moving_time:
        activity.moving_time = new_moving_time
        return True
    else:
        return False


def enrichment_copy_latlon(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    if activity.start_latitude is None:
        activity.start_latitude = time_series["latitude"].iloc[0]
        activity.end_latitude = time_series["latitude"].iloc[-1]
        activity.start_longitude = time_series["longitude"].iloc[0]
        activity.end_longitude = time_series["longitude"].iloc[-1]
        return True
    else:
        return False


enrichments: list[Callable[[Activity, pd.DataFrame, Config], bool]] = [
    enrichment_set_timezone,
    enrichment_normalize_time,
    enrichment_rename_altitude,
    enrichment_compute_tile_xy,
    # enrichment_copernicus_elevation,
    enrichment_elevation_gain,
    enrichment_add_calories,
    enrichment_distance,
    enrichment_moving_time,
    enrichment_copy_latlon,
]


def apply_enrichments(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> bool:
    was_changed = False
    for enrichment in enrichments:
        was_changed |= enrichment(activity, time_series, config)
    return was_changed


def update_and_commit(
    activity: Activity, time_series: pd.DataFrame, config: Config
) -> None:
    changed = apply_enrichments(activity, time_series, config)
    if not activity.time_series_uuid:
        activity.time_series_uuid = str(uuid.uuid4())
    if changed:
        activity.replace_time_series(time_series)
    DB.session.add(activity)
    DB.session.commit()
