import datetime
import logging
import uuid
import zoneinfo
from collections.abc import Callable

import numpy as np
import pandas as pd

from .coordinates import get_distance
from .datamodel import DB, Activity, ActivityImportConfig
from .missing_values import some
from .tag_extraction import apply_tag_extraction_from_database
from .tiles import compute_tile_float
from .time_conversion import get_timezone

logger = logging.getLogger(__name__)


def _clamp_index(index: int, length: int) -> int:
    """Keep a positional index within a series of the given length."""
    if index < 0:
        return index
    return min(index, length - 1)


def enrichment_set_timezone(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    assert len(time_series) > 0, (
        f"You cannot import an activity without points. {activity=}"
    )
    latitude, longitude = time_series[["latitude", "longitude"]].iloc[0].to_list()
    if activity.iana_timezone is None or activity.start_country is None:
        activity.iana_timezone = get_timezone(latitude, longitude)
        return True
    else:
        return False


def enrichment_normalize_time(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
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
        time_series["time"] = (
            time_series["time"].dt.tz_convert(tz_utc).astype("datetime64[ns, UTC]")
        )
        changed = True

    assert pd.api.types.is_dtype_equal(
        time_series["time"].dtype, "datetime64[ns, UTC]"
    ), (
        time_series["time"].dtype,
        time_series["time"].iloc[0],
    )

    new_start = some(
        time_series["time"].iloc[
            _clamp_index(activity.index_begin or 0, len(time_series))
        ]
    )
    if new_start != activity.start:
        activity.start = new_start
        changed = True

    new_elapsed_time = some(
        time_series["time"].iloc[
            _clamp_index(activity.index_end or -1, len(time_series))
        ]
        - time_series["time"].iloc[
            _clamp_index(activity.index_begin or 0, len(time_series))
        ]
    )
    if new_elapsed_time != activity.elapsed_time:
        activity.elapsed_time = new_elapsed_time
        changed = True

    return changed


def enrichment_rename_altitude(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    if "altitude" in time_series.columns:
        time_series.rename(columns={"altitude": "elevation"}, inplace=True)
        return True
    else:
        return False


def enrichment_compute_tile_xy(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    x_missing = "x" not in time_series.columns
    y_missing = "y" not in time_series.columns
    xy_invalid = (
        not x_missing
        and not y_missing
        and not (
            np.isfinite(time_series["x"]).all() and np.isfinite(time_series["y"]).all()
        )
    )
    if force or x_missing or y_missing or xy_invalid:
        x, y = compute_tile_float(time_series["latitude"], time_series["longitude"], 0)
        time_series["x"] = x
        time_series["y"] = y
        return True
    else:
        return False


def enrichment_copernicus_elevation(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
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
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    if (
        "elevation" in time_series.columns
        or "copernicus_elevation" in time_series.columns
    ) and ("elevation_gain_cum" not in time_series.columns or force):
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
            time_series["elevation_gain_cum"].iloc[
                _clamp_index(activity.index_end or -1, len(time_series))
            ]
            - time_series["elevation_gain_cum"].iloc[
                _clamp_index(activity.index_begin or 0, len(time_series))
            ]
        )
        return True
    else:
        return False


def enrichment_add_calories(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    if "calories" in time_series.columns and (activity.calories is None or force):
        activity.calories = (
            time_series["calories"].iloc[
                _clamp_index(activity.index_end or -1, len(time_series))
            ]
            - time_series["calories"].iloc[
                _clamp_index(activity.index_begin or 0, len(time_series))
            ]
        )
        return True
    else:
        return False


def enrichment_distance(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
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
            / time_series["time"].diff().dt.total_seconds()
            * 3600
        )
        # Division by zero causes infinity. We replace these with NaN and interpolate the values instead.
        time_series["speed"] = time_series["speed"].replace(
            [0, np.inf, -np.inf], np.nan
        )
        time_series.interpolate(inplace=True)

        changed = True

    # A GPS spike is a point where speed rose sharply AND drops sharply at the next sample.
    # We measure the rate of change in km/h per second (acceleration) rather than raw km/h
    # per sample, so the threshold is independent of the GPS sampling interval.
    # The bilateral check (rise AND fall) leaves legitimate sustained high speeds intact.
    time_diff_s = time_series["time"].diff().dt.total_seconds()
    time_diff_s_next = (-time_series["time"].diff(-1)).dt.total_seconds()
    speed_rise_rate = time_series["speed"].diff() / time_diff_s
    speed_fall_rate = time_series["speed"].diff(-1) / time_diff_s_next
    spike_acceleration_threshold = 20.0  # km/h per second ≈ 5.6 m/s²
    is_spike = (speed_rise_rate > spike_acceleration_threshold) & (
        speed_fall_rate > spike_acceleration_threshold
    )
    if is_spike.any():
        time_series.loc[is_spike, "speed"] = np.nan
        time_series["speed"] = time_series["speed"].interpolate()
        changed = True

    if "segment_id" not in time_series.columns:
        if config.time_diff_threshold_seconds:
            time_series["segment_id"] = np.cumsum(jump_indices)
        else:
            time_series["segment_id"] = 0
        changed = True

    new_distance_km = (
        time_series["distance_km"].iloc[
            _clamp_index(activity.index_end or -1, len(time_series))
        ]
        - time_series["distance_km"].iloc[
            _clamp_index(activity.index_begin or 0, len(time_series))
        ]
    )
    if new_distance_km != activity.distance_km:
        activity.distance_km = new_distance_km
        changed = True

    return changed


def enrichment_moving_time(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    def moving_time(group) -> datetime.timedelta:
        selection = group["speed"] > 1.0
        time_diff = group["time"].diff().loc[selection]
        return time_diff.sum()

    new_moving_time = (
        time_series.iloc[activity.index_begin or 0 : activity.index_end or -1]
        .groupby("segment_id")
        .apply(moving_time, include_groups=False)
        .sum()
    )
    if new_moving_time != activity.moving_time:
        activity.moving_time = new_moving_time
        return True
    else:
        return False


def enrichment_copy_latlon(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    if activity.start_latitude is None or force:
        activity.start_latitude = time_series["latitude"].iloc[
            _clamp_index(activity.index_begin or 0, len(time_series))
        ]
        activity.end_latitude = time_series["latitude"].iloc[
            _clamp_index(activity.index_end or -1, len(time_series))
        ]
        activity.start_longitude = time_series["longitude"].iloc[
            _clamp_index(activity.index_begin or 0, len(time_series))
        ]
        activity.end_longitude = time_series["longitude"].iloc[
            _clamp_index(activity.index_end or -1, len(time_series))
        ]
        return True
    else:
        return False


enrichments: list[
    Callable[[Activity, pd.DataFrame, ActivityImportConfig, bool], bool]
] = [
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
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool,
) -> bool:
    was_changed = False
    for enrichment in enrichments:
        was_changed |= enrichment(activity, time_series, config, force)
    return was_changed


def update_and_commit(
    activity: Activity,
    time_series: pd.DataFrame,
    config: ActivityImportConfig,
    force: bool = False,
) -> None:
    if len(time_series) < 2:
        logger.warning(
            "Skipping activity %r because it has fewer than two track points.",
            activity.path or activity.upstream_id or activity.name or "<unknown>",
        )
        return

    if activity.id is None:
        apply_tag_extraction_from_database(activity)
    changed = apply_enrichments(activity, time_series, config, force)
    if not activity.time_series_uuid:
        activity.time_series_uuid = str(uuid.uuid4())
    if changed:
        activity.replace_time_series(time_series)
    DB.session.add(activity)
    DB.session.commit()
