import numpy as np
import pandas as pd


def convert_to_datetime_ns(date) -> np.datetime64 | pd.Series:
    if isinstance(date, pd.Series):
        ts = pd.to_datetime(date)
        ts = ts.dt.tz_localize(None)
        return ts
    else:
        ts = pd.to_datetime(date)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        return ts.to_datetime64()
