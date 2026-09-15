from geo_activity_playground.core.time_conversion import (
    get_timezone,
)


def test_timezone_finder() -> None:
    iana_timezone = get_timezone(50, 7)
    assert iana_timezone == "Europe/Berlin"
