import numpy as np


def get_distance(latlon_1: tuple[float, float], latlon_2: tuple[float, float]) -> float:
    """
    https://en.wikipedia.org/wiki/Haversine_formula
    """
    earth_radius = 6371e3
    lat_1 = np.radians(latlon_1[0])
    lon_1 = np.radians(latlon_1[1])
    lat_2 = np.radians(latlon_2[0])
    lon_2 = np.radians(latlon_2[1])

    lat_diff = lat_2 - lat_1
    lon_diff = lon_2 - lon_1
    a = (
        np.sin(lat_diff / 2) ** 2
        + np.cos(lat_1) * np.cos(lat_2) * np.sin(lon_diff / 2) ** 2
    )
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return earth_radius * c
