import math
from typing import Tuple

import numpy as np


def compute_tile(lat: float, lon: float, zoom: int = 14) -> Tuple[int, int]:
    x = np.radians(lon)
    y = np.arcsinh(np.tan(np.radians(lat)))
    x = (1 + x/np.pi)/2
    y = (1 - y/np.pi)/2
    n = 2**zoom
    return int(x * n), int(y * n)


def get_tile_upper_left_lat_lon(tile_x: int, tile_y: int, zoom: int) -> Tuple[float, float]:
  n = 2.0 ** zoom
  lon_deg = tile_x / n * 360.0 - 180.0
  lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * tile_y / n)))
  lat_deg = math.degrees(lat_rad)
  return lat_deg, lon_deg