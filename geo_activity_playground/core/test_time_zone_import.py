import datetime
import pathlib
import zoneinfo

from ..importers.activity_parsers import read_activity
from .time_conversion import sanitize_datetime


def test_time_zone_from_string() -> None:
    """
    Understanding test for zoneinfo.

    A user from Helsinki has recorded an activity. His device recorded 2025-06-21 14:41:06 in UTC. The local time was 17:41:06. How would we represent that properly? We need to import the time as UTC and then convert into the Helsinki time zone. At the end we drop the time zone information to make it a “naive” time but with the local time zone.
    """
    tz_helsinki = zoneinfo.ZoneInfo("Europe/Helsinki")
    tz_utc = zoneinfo.ZoneInfo("UTC")
    dt_utc = datetime.datetime(2025, 6, 21, 14, 41, 6, tzinfo=tz_utc)
    dt_helsinki = dt_utc.astimezone(tz_helsinki)
    assert dt_helsinki == datetime.datetime(2025, 6, 21, 17, 41, 6, tzinfo=tz_helsinki)
    assert dt_helsinki.replace(tzinfo=None) == datetime.datetime(2025, 6, 21, 17, 41, 6)


def test_utc_to_helsinki() -> None:
    assert sanitize_datetime(
        datetime.datetime(2025, 6, 21, 14, 41, 6, tzinfo=zoneinfo.ZoneInfo("UTC")),
        fallback_from="UTC",
        fallback_to="Europe/Helsinki",
    ) == datetime.datetime(
        2025, 6, 21, 17, 41, 6, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
    )


def test_0200_to_helsinki() -> None:
    assert sanitize_datetime(
        datetime.datetime(
            2025,
            6,
            21,
            16,
            41,
            6,
            tzinfo=datetime.timezone(datetime.timedelta(hours=2)),
        ),
        fallback_from="UTC",
        fallback_to="Europe/Helsinki",
    ) == datetime.datetime(
        2025, 6, 21, 17, 41, 6, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
    )


def test_naive_utc_to_helsinki() -> None:
    assert sanitize_datetime(
        datetime.datetime(2025, 6, 21, 14, 41, 6),
        fallback_from="UTC",
        fallback_to="Europe/Helsinki",
    ) == datetime.datetime(
        2025, 6, 21, 17, 41, 6, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
    )


def test_naive_helsinki_to_helsinki() -> None:
    assert sanitize_datetime(
        datetime.datetime(2025, 6, 21, 17, 41, 6),
        fallback_from="Europe/Helsinki",
        fallback_to="Europe/Helsinki",
    ) == datetime.datetime(
        2025, 6, 21, 17, 41, 6, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
    )


def test_time_zone_from_abvio() -> None:
    """
    Apply local time zone from Abvio generated files.

    As reported in https://github.com/martin-ueding/geo-activity-playground/issues/303, the GPX files from Abvio contain the time data as UTC, but there is a field `abvio:startTimeZone` which contains it.

    ```
    <desc>Cyclemeter Row 21. Jun 2025 at 17.41.06</desc>
    <time>2025-06-21T15:10:41Z</time>
    <trkpt lat="…" lon="…"><ele>137.7</ele><time>2025-06-21T14:41:06Z</time></trkpt>
    ...
    <abvio:startTime>2025-06-21 14:41:06.537</abvio:startTime>
    <abvio:startTimeZone>Europe/Helsinki</abvio:startTimeZone>
    ```
    """
    path = pathlib.Path(
        "/home/mu/Dokumente/Geo Activity Playground/Test-Suite/b1b9ec9b-016a-4223-9218-12b97d7019f2.gpx"
    )
    meta, ts = read_activity(path)

    assert ts["time"].iloc[0] == datetime.datetime(
        2025, 6, 21, 17, 41, 6, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
    )
