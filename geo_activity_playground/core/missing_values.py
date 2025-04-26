from typing import Optional
from typing import Union

import numpy as np


def some(value) -> Optional[Union[float, int]]:
    if value is None:
        return None
    elif np.isnan(value):
        return None
    else:
        return value
