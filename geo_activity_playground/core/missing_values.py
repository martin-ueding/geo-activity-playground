from typing import Any

import pandas as pd


def some(value: Any) -> Any | None:
    if value is None:
        return None
    elif pd.isna(value):
        return None
    else:
        return value
