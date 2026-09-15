import datetime
import json
import logging
import zoneinfo

import pandas as pd
import requests
import timezonefinder

from .paths import USER_CACHE_DIR

logger = logging.getLogger(__name__)


def sanitize_datetime(
    dt: datetime.datetime, fallback_from: str, fallback_to: str
) -> datetime.datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(fallback_from))
    return dt.astimezone(zoneinfo.ZoneInfo(fallback_to))


def local_ymd_from_utc(
    event_time: datetime.datetime | pd.Timestamp | None,
    activity_start: datetime.datetime | pd.Timestamp | None,
    iana_timezone: str | None,
) -> tuple[int | None, int | None, int | None]:
    """Calendar date an event falls on in the recording activity's timezone.

    Times are stored in UTC, so a late evening ride would otherwise be filed
    under the following day east of Greenwich. The activity start stands in
    when the event itself carries no time.
    """
    if event_time is None or pd.isna(event_time):
        if activity_start is None or pd.isna(activity_start):
            return None, None, None
        timestamp = pd.Timestamp(activity_start)
    else:
        timestamp = pd.Timestamp(event_time)
    if timestamp.tz is None:
        timestamp = timestamp.tz_localize(zoneinfo.ZoneInfo("UTC"))

    timezone_name = "UTC" if iana_timezone is None else iana_timezone
    try:
        timezone = zoneinfo.ZoneInfo(timezone_name)
    except zoneinfo.ZoneInfoNotFoundError:
        timezone = zoneinfo.ZoneInfo("UTC")
    local = timestamp.tz_convert(timezone)
    return int(local.year), int(local.month), int(local.day)


def local_date_from_utc(
    event_time: datetime.datetime | pd.Timestamp | None,
    activity_start: datetime.datetime | pd.Timestamp | None,
    iana_timezone: str | None,
) -> datetime.date | None:
    year, month, day = local_ymd_from_utc(event_time, activity_start, iana_timezone)
    if year is None or month is None or day is None:
        return None
    return datetime.date(year, month, day)


def get_timezone(latitude: float, longitude: float) -> str | None:
    tf = timezonefinder.TimezoneFinder()  # reuse
    return tf.timezone_at(lng=longitude, lat=latitude)
