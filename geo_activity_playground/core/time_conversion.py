import datetime
import zoneinfo

import numpy as np
import pandas as pd


def convert_to_datetime_ns(date) -> np.datetime64 | pd.Series:
    if isinstance(date, pd.Series):
        ts = pd.to_datetime(date)
        return ts
    else:
        ts = pd.to_datetime(date)
        return ts.to_datetime64()


def sanitize_datetime(
    dt: datetime.datetime, fallback_from: str, fallback_to: str
) -> datetime.datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(fallback_from))
    return dt.astimezone(zoneinfo.ZoneInfo(fallback_to))
