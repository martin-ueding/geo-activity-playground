import typing

import numpy as np
import pandas as pd


class Bounds:
    def __init__(self, x_min: int, y_min: int, x_max: int, y_max: int) -> None:
        assert x_min <= x_max
        assert y_min <= y_max

        self.x_min = x_min
        self.y_min = y_min
        self.x_max = x_max
        self.y_max = y_max

    def contains(self, x: int, y: int) -> bool:
        return (self.x_min < x < self.x_max) and (self.y_min < y < self.y_max)


FloatOrSeries = typing.TypeVar("FloatOrSeries", float, np.ndarray, pd.Series)


def get_distance(
    lat_1: FloatOrSeries,
    lon_1: FloatOrSeries,
    lat_2: FloatOrSeries,
    lon_2: FloatOrSeries,
) -> FloatOrSeries:
    """
    https://en.wikipedia.org/wiki/Haversine_formula
    """
    earth_radius = 6371e3
    lat_1 = np.radians(lat_1)
    lon_1 = np.radians(lon_1)
    lat_2 = np.radians(lat_2)
    lon_2 = np.radians(lon_2)
    lat_diff = lat_2 - lat_1
    lon_diff = lon_2 - lon_1
    a = (
        np.sin(lat_diff / 2) ** 2
        + np.cos(lat_1) * np.cos(lat_2) * np.sin(lon_diff / 2) ** 2
    )
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return earth_radius * c
