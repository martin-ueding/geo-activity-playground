import datetime

import numpy as np
import pandas as pd

from .time_conversion import convert_to_datetime_ns

target = np.datetime64(datetime.datetime(2000, 1, 2, 3, 4, 5))


def test_convert_to_datetime_ns() -> None:
    inputs = [
        datetime.datetime(2000, 1, 2, 3, 4, 5),
    ]

    for d in inputs:
        actual = convert_to_datetime_ns(d)
        assert pd.api.types.is_dtype_equal(actual.dtype, "datetime64[ns]")
