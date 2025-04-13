import datetime

from .strava_api import round_to_next_quarter_hour


def test_round_to_next_quarter_hour() -> None:
    assert round_to_next_quarter_hour(
        datetime.datetime(2023, 12, 13, 7, 22, 17)
    ) == datetime.datetime(2023, 12, 13, 7, 30, 0)
    assert round_to_next_quarter_hour(
        datetime.datetime(2023, 12, 13, 7, 58, 17)
    ) == datetime.datetime(2023, 12, 13, 8, 0, 0)
