"""Detection of the locations where the athlete was stationary.

A dwell is a maximal run of consecutive points that all lie within the place
radius of the run's first point and span at least the minimum stay duration.
This also covers a gap in the recording from an auto-pause: two consecutive
points close to each other form such a run if their time difference is large
enough.
"""

import datetime

import numpy as np
import pandas as pd

from ...core.coordinates import get_distance
from .model import MIN_STAY_DURATION, PLACE_RADIUS_M, Stay, StayKind

ENDPOINT_POINTS = 5


def detect_stays(time_series: pd.DataFrame) -> list[Stay]:
    finite = np.isfinite(time_series["latitude"]) & np.isfinite(
        time_series["longitude"]
    )
    time_series = time_series.loc[finite]
    if time_series.empty:
        return []
    lat = time_series["latitude"].to_numpy()
    lon = time_series["longitude"].to_numpy()
    time = (
        time_series["time"]
        if "time" in time_series.columns
        else pd.Series(pd.NaT, index=time_series.index)
    )

    stays = [
        Stay(
            kind=StayKind.START,
            latitude=float(np.median(lat[:ENDPOINT_POINTS])),
            longitude=float(np.median(lon[:ENDPOINT_POINTS])),
            departure=_to_naive_utc(time.iloc[0]),
        )
    ]
    seconds = (time - time.min()).dt.total_seconds().to_numpy()
    for begin, end in dwell_ranges(lat, lon, seconds):
        stays.append(
            Stay(
                kind=StayKind.DWELL,
                latitude=float(np.mean(lat[begin:end])),
                longitude=float(np.mean(lon[begin:end])),
                arrival=_to_naive_utc(time.iloc[begin]),
                departure=_to_naive_utc(time.iloc[end - 1]),
            )
        )
    stays.append(
        Stay(
            kind=StayKind.END,
            latitude=float(np.median(lat[-ENDPOINT_POINTS:])),
            longitude=float(np.median(lon[-ENDPOINT_POINTS:])),
            arrival=_to_naive_utc(time.iloc[-1]),
        )
    )
    for sequence, stay in enumerate(stays):
        stay.sequence = sequence
    return stays


def dwell_ranges(
    lat: np.ndarray, lon: np.ndarray, seconds: np.ndarray
) -> list[tuple[int, int]]:
    """Half-open index ranges of the dwells, chosen greedily from the start."""
    ranges = []
    next_begin = 0
    for begin in np.flatnonzero(_lasts_long_enough(lat, lon, seconds)):
        if begin >= next_begin:
            next_begin = _run_end(lat, lon, begin)
            ranges.append((int(begin), next_begin))
    return ranges


def _lasts_long_enough(
    lat: np.ndarray, lon: np.ndarray, seconds: np.ndarray
) -> np.ndarray:
    """Whether the run starting at each point spans the minimum stay duration.

    A run is only followed until it reaches the duration, which bounds the
    number of iterations by the number of points within that duration.
    """
    n = len(lat)
    result = np.zeros(n, dtype=bool)
    open_runs = np.flatnonzero(np.isfinite(seconds))
    offset = 1
    while len(open_runs):
        candidate = open_runs + offset
        open_runs = open_runs[candidate < n]
        candidate = candidate[candidate < n]
        within = (
            get_distance(lat[open_runs], lon[open_runs], lat[candidate], lon[candidate])
            <= PLACE_RADIUS_M
        )
        open_runs = open_runs[within]
        candidate = candidate[within]
        reached = (
            seconds[candidate] - seconds[open_runs] >= MIN_STAY_DURATION.total_seconds()
        )
        result[open_runs[reached]] = True
        open_runs = open_runs[~reached]
        offset += 1
    return result


def _run_end(lat: np.ndarray, lon: np.ndarray, begin: int) -> int:
    """The first index after `begin` that lies outside of its radius."""
    outside = np.flatnonzero(
        get_distance(lat[begin], lon[begin], lat[begin + 1 :], lon[begin + 1 :])
        > PLACE_RADIUS_M
    )
    return begin + 1 + int(outside[0]) if len(outside) else len(lat)


def _to_naive_utc(time: pd.Timestamp) -> datetime.datetime | None:
    if pd.isna(time):
        return None
    if time.tzinfo is not None:
        time = time.tz_convert("UTC").tz_localize(None)
    return time.to_pydatetime()
