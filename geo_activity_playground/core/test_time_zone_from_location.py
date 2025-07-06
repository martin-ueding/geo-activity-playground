from .time_conversion import get_country_timezone


def test_time_zone_from_location() -> None:
    country, iana_timezone = get_country_timezone(50, 7)
    assert country == "Germany"
    assert iana_timezone == "Europe/Berlin"
