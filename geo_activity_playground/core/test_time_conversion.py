import datetime

import numpy as np
import pandas as pd

from .time_conversion import convert_to_datetime_ns

target = np.datetime64(datetime.datetime(2000, 1, 2, 3, 4, 5))


def test_convert_to_datetime_ns() -> None:
    dt_local = datetime.datetime(2000, 1, 2, 3, 4, 5)
    dt_tz = datetime.datetime(
        2000, 1, 2, 3, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=3))
    )
    dt_utc = datetime.datetime(2000, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)

    inputs = [
        dt_local,
        dt_tz,
        dt_utc,
        pd.Timestamp(dt_local),
        pd.Timestamp(dt_tz),
        pd.Timestamp(dt_utc),
    ]

    for d in inputs:
        actual = convert_to_datetime_ns(d)
        # assert pd.api.types.is_dtype_equal(actual.dtype, "datetime64[ns]")
        assert actual == target

        actual = convert_to_datetime_ns(pd.Series([d]))
        assert actual.iloc[0] == target


def test_NaT() -> None:
    assert pd.isna(convert_to_datetime_ns(pd.NaT))
