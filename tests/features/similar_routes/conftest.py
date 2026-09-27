"""Synthetic tracks along an east-west road."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

LAT = 51.5
LON = 7.0
METERS_PER_DEGREE = 111_320.0


def _road(
    begin_m: float, end_m: float, step_m: float, north_m: float = 0.0
) -> pd.DataFrame:
    east_m = np.append(np.arange(begin_m, end_m, step_m), end_m)
    return pd.DataFrame(
        {
            "latitude": LAT + north_m / METERS_PER_DEGREE,
            "longitude": LON + east_m / (METERS_PER_DEGREE * np.cos(np.radians(LAT))),
            "segment_id": 0,
        }
    )


@pytest.fixture
def road() -> Callable[..., pd.DataFrame]:
    return _road
