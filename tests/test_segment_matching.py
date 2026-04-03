from types import SimpleNamespace

import pandas as pd
import pytest

from geo_activity_playground.core.config import Config
from geo_activity_playground.core.segments import segment_track_distance


def make_activity(coordinates: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(
        time_series=pd.DataFrame(
            {
                "latitude": [lat for lat, _ in coordinates],
                "longitude": [lon for _, lon in coordinates],
            }
        )
    )


def make_segment(coordinates: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(coordinates=coordinates)


def first_distance(segment, activity, config: Config) -> float:
    matches = list(segment_track_distance(segment, activity, config))
    assert len(matches) == 1
    distance_m, _ = matches[0]
    return float(distance_m)


def test_segment_distance_zero_when_segment_is_contained() -> None:
    config = Config(segment_split_distance=150)
    segment = make_segment([[0.0, 0.0], [0.0, 0.001]])
    activity = make_activity(
        [
            [0.0, -0.002],
            [0.0, 0.0],
            [0.0, 0.001],
            [0.0, 0.0015],
            [0.0, 0.003],
        ]
    )

    distance_m = first_distance(segment, activity, config)
    assert distance_m == pytest.approx(0.0, abs=1e-9)


def test_segment_distance_positive_for_crossing_line() -> None:
    config = Config(segment_split_distance=300)
    segment = make_segment([[0.0, 0.0], [0.0, 0.001], [0.0, 0.002]])
    activity = make_activity(
        [
            [-0.01, 0.001],
            [-0.001, 0.001],
            [0.0, 0.001],
            [0.001, 0.001],
            [0.01, 0.001],
        ]
    )

    distance_m = first_distance(segment, activity, config)
    assert distance_m > 0.0


def test_sparse_collinear_overlap_has_zero_distance() -> None:
    config = Config(segment_split_distance=100)
    segment = make_segment([[0.0, 0.0005], [0.0, 0.0015]])
    activity = make_activity(
        [
            [0.0, -0.01],
            [0.0, 0.0],
            [0.0, 0.002],
            [0.0, 0.01],
        ]
    )

    distance_m = first_distance(segment, activity, config)
    assert distance_m == pytest.approx(0.0, abs=1e-9)
