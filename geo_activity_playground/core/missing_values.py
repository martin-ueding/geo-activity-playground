from typing import Any
from typing import Optional

import numpy as np
import pandas as pd


def some(value: Any) -> Optional[Any]:
    if value is None:
        return None
    elif pd.isna(value):
        return None
    else:
        return value
