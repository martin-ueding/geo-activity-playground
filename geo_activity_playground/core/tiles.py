import logging
import math
from typing import Iterator
from typing import Optional

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


def compute_tile_float(
    lat: float | pd.Series, lon: float | pd.Series, zoom: int
) -> tuple[float, float]:
    x = np.radians(lon)
    y = np.arcsinh(np.tan(np.radians(lat)))
    x = (1 + x / np.pi) / 2
    y = (1 - y / np.pi) / 2
    n = 2**zoom
    return x * n, y * n


def compute_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    x, y = compute_tile_float(lat, lon, zoom)
    return int(x), int(y)


def get_tile_upper_left_lat_lon(
    tile_x: int, tile_y: int, zoom: int
) -> tuple[float, float]:
    n = 2.0**zoom
    lon_deg = tile_x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * tile_y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def xy_to_latlon(x: float, y: float, zoom: int) -> tuple[float, float]:
    """
    Returns (lat, lon) in degree from OSM coordinates (x,y) rom https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames

    Based on https://github.com/remisalmon/Strava-local-heatmap.
    """
    n = 2.0**zoom
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * y / n)))
    lat_deg = float(np.degrees(lat_rad))
    return lat_deg, lon_deg


def interpolate_missing_tile(
    x1: float, y1: float, x2: float, y2: float
) -> Optional[tuple[int, int]]:
    # We are only interested in diagonal tile combinations, therefore we skip adjacent ones.
    if int(x1) == int(x2) or int(y1) == int(y2):
        return None

    # Some people have large jumps in their tracks. We don't want to interpolate when there is more than tile in between.
    if abs(int(x1) - int(x2)) > 1 or abs(int(y1) - int(y2)) > 1:
        return None

    x_hat = int(max(x1, x2))
    l = (x_hat - x1) / (x2 - x1)
    y_hat = int(y1 + l * (y2 - y1))
    if y_hat == int(y1):
        return (int(x2), y_hat)
    else:
        return (int(x1), y_hat)


def adjacent_to(tile: tuple[int, int]) -> Iterator[tuple[int, int]]:
    x, y = tile
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)
