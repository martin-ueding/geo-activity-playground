import numpy as np
import pandas as pd


def convert_to_datetime_ns(date) -> np.datetime64:
    ts = pd.to_datetime(date)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.to_datetime64()
