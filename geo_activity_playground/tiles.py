from typing import Tuple

import numpy as np


def compute_tile(lat: float, lon: float, zoom: int = 14) -> Tuple[int, int]:
    x = np.radians(lon)
    y = np.arcsinh(np.tan(np.radians(lat)))
    x = (1 + x/np.pi)/2
    y = (1 - y/np.pi)/2
    n = 2**zoom
    return int(x * n), int(y * n)