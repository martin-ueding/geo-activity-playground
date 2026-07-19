import datetime

from .datamodel import Activity


def test_no_duration() -> None:
    activity = Activity(name="Test", distance_km=10.0)
    assert activity.average_speed_elapsed_kmh is None
    assert activity.average_speed_moving_kmh is None


def test_zero_duration() -> None:
    activity = Activity(
        name="Test",
        distance_km=10.0,
        elapsed_time=datetime.timedelta(seconds=0),
        moving_time=datetime.timedelta(seconds=0),
    )
    assert activity.average_speed_elapsed_kmh is None
    assert activity.average_speed_moving_kmh is None
