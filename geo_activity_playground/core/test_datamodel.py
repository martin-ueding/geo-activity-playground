from .datamodel import Activity


def test_zero_duration() -> None:
    activity = Activity(name="Test", distance_km=10.0)
    assert activity.average_speed_elapsed_kmh is None
    assert activity.average_speed_moving_kmh is None
