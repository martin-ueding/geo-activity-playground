import datetime

import pandas as pd
import pytest

from .summary_stats import get_equipment_use_table


@pytest.fixture
def activity_meta() -> pd.DataFrame:
    """
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
    moving_time: datetime.timedelta
    name: str
    path: str
    start_latitude: float
    start_longitude: float
    start: np.datetime64
    steps: int
    """
    return pd.DataFrame(
        {
            "calories": pd.Series([None, 1000, 2000]),
            "commute": pd.Series([True, False, True]),
            "consider_for_achievements": pd.Series([True, True, False]),
            "distance_km": pd.Series([9.8, 4.4, 4.3]),
            "elapsed_time": pd.Series(
                [
                    datetime.timedelta(minutes=0.34),
                    datetime.timedelta(minutes=0.67),
                    None,
                ]
            ),
            "end_latitude": pd.Series([0.58, 0.5, 0.19]),
            "end_longitude": pd.Series([0.2, 0.94, 0.69]),
            "equipment": pd.Series(["A", "B", "B"]),
            "id": pd.Series([1, 2, 3]),
            "kind": pd.Series(["X", "X", "Y"]),
            "moving_time": pd.Series(
                [
                    datetime.timedelta(minutes=0.32),
                    datetime.timedelta(minutes=0.83),
                    None,
                ]
            ),
            "name": pd.Series(["Test1", "Test2", "Test1"]),
            "path": pd.Series(["Test1.fit", "Test2.gpx", "Test1.kml"]),
            "start_latitude": pd.Series([0.22, 0.02, 0.35]),
            "start_longitude": pd.Series([0.95, 0.95, 0.81]),
            "start": pd.Series(
                [
                    datetime.datetime(2024, 12, 24, 10),
                    datetime.datetime(2025, 1, 1, 10),
                    None,
                ]
            ),
            "steps": pd.Series([1234, None, 5432]),
        }
    )


def test_activity_meta(activity_meta) -> None:
    print()
    print(activity_meta)


def test_equipment_use_table(activity_meta) -> None:
    activity_meta = pd.DataFrame(
        {
            "distance_km": pd.Series([9.8, 4.4, 4.3]),
            "equipment": pd.Series(["A", "B", "B"]),
            "start": pd.Series(
                [
                    datetime.datetime(2024, 12, 24, 10),
                    datetime.datetime(2025, 1, 1, 10),
                    None,
                ]
            ),
        }
    )

    offsets = {"A": 4.0}

    expected = [
        {
            "equipment": "B",
            "total_distance_km": 9,
            "first_use": "2025-01-01",
            "last_use": "2025-01-01",
        },
        {
            "equipment": "A",
            "total_distance_km": 14,
            "first_use": "2024-12-24",
            "last_use": "2024-12-24",
        },
    ]
    actual = get_equipment_use_table(activity_meta, offsets)
    assert actual == expected
