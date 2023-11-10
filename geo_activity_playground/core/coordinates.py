import numpy as np


def get_distance(lat_1: float, lon_1: float, lat_2: float, lon_2: float) -> float:
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
