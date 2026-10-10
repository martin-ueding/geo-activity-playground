import datetime

import numpy as np
import pandas as pd

from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.features.places.stays import detect_stays

LAT = 51.5
LON = 7.0
METERS_PER_DEGREE = 111_320.0
T0 = pd.Timestamp("2024-05-01 08:00", tz="UTC")


def _track(east_m: np.ndarray, seconds: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": LAT,
            "longitude": LON + east_m / (METERS_PER_DEGREE * np.cos(np.radians(LAT))),
            "time": T0 + pd.to_timedelta(seconds, unit="s"),
        }
    )


def _ride_with_stop(stop_s: int) -> pd.DataFrame:
    """Riding east at 5 m/s, stopping at 1 km with jitter, then riding on."""
    before = np.arange(0, 200) * 5.0
    stop = 1000.0 + 5.0 * np.sin(np.arange(stop_s))
    after = 1000.0 + np.arange(1, 200) * 5.0
    east_m = np.concatenate([before, stop, after])
    return _track(east_m, np.arange(len(east_m)))


def test_stop_becomes_a_dwell() -> None:
    stays = detect_stays(_ride_with_stop(300))

    assert [stay.kind for stay in stays] == ["start", "dwell", "end"]
    assert [stay.sequence for stay in stays] == [0, 1, 2]
    dwell = stays[1]
    stop_lon = LON + 1000.0 / (METERS_PER_DEGREE * np.cos(np.radians(LAT)))
    assert get_distance(dwell.latitude, dwell.longitude, LAT, stop_lon) < 10
    assert dwell.arrival is not None and dwell.departure is not None
    assert dwell.departure - dwell.arrival >= datetime.timedelta(minutes=5)
    assert dwell.arrival.tzinfo is None


def test_short_stop_is_ignored() -> None:
    stays = detect_stays(_ride_with_stop(60))

    assert [stay.kind for stay in stays] == ["start", "end"]


def test_recording_gap_becomes_a_dwell() -> None:
    east_m = np.array([0.0, 500.0, 1000.0, 1010.0, 1500.0, 2000.0])
    seconds = np.array([0, 100, 200, 800, 900, 1000])

    stays = detect_stays(_track(east_m, seconds))

    assert [stay.kind for stay in stays] == ["start", "dwell", "end"]
    gap_lon = LON + 1005.0 / (METERS_PER_DEGREE * np.cos(np.radians(LAT)))
    assert get_distance(stays[1].latitude, stays[1].longitude, LAT, gap_lon) < 1


def test_route_without_time_has_only_start_and_end() -> None:
    track = _ride_with_stop(300)
    track["time"] = pd.NaT

    stays = detect_stays(track)

    assert [stay.kind for stay in stays] == ["start", "end"]
    assert stays[0].departure is None


def test_start_ignores_outlier_of_cold_start() -> None:
    track = _track(np.arange(0, 50) * 5.0, np.arange(50))
    track.loc[0, "latitude"] = LAT + 0.01

    start = detect_stays(track)[0]

    assert get_distance(start.latitude, start.longitude, LAT, LON) < 20
