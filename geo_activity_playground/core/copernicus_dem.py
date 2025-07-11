import functools
import math
import pathlib
from typing import Optional

import boto3
import botocore.config
import botocore.exceptions
import geotiff
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from .paths import USER_CACHE_DIR


def _s3_path(lat: int, lon: int) -> pathlib.Path:
    lat_str = f"N{(lat):02d}" if lat >= 0 else f"S{(-lat):02d}"
    lon_str = f"E{(lon):03d}" if lon >= 0 else f"W{(-lon):03d}"
    result = (
        USER_CACHE_DIR
        / "Copernicus DEM"
        / f"Copernicus_DSM_COG_30_{lat_str}_00_{lon_str}_00_DEM.tif"
    )

    result.parent.mkdir(exist_ok=True)
    return result


def _ensure_copernicus_file(p: pathlib.Path) -> None:
    if p.exists():
        return
    s3 = boto3.client(
        "s3", config=botocore.config.Config(signature_version=botocore.UNSIGNED)
    )
    try:
        s3.download_file("copernicus-dem-90m", f"{p.stem}/{p.name}", p)
    except botocore.exceptions.ClientError as e:
        pass


@functools.lru_cache(9)
def _get_elevation_arrays(p: pathlib.Path) -> Optional[np.ndarray]:

    _ensure_copernicus_file(p)
    if not p.exists():
        return None

    gt = geotiff.GeoTiff(p)
    a = np.array(gt.read())
    lon_array, lat_array = gt.get_coord_arrays()
    return np.stack([a, lat_array, lon_array], axis=0)


@functools.lru_cache(1)
def _get_interpolator(lat: int, lon: int) -> Optional[RegularGridInterpolator]:
    arrays = _get_elevation_arrays(_s3_path(lat, lon))
    # If we don't have data for the current center, we cannot do anything.
    if arrays is None:
        return None

    # # Take a look at the neighbors. If all 8 neighbor grid cells are present, we can
    # neighbor_shapes = [
    #     get_elevation_arrays(s3_path(lat + lat_offset, lon + lon_offset)).shape
    #     for lon_offset in [-1, 0, 1]
    #     for lat_offset in [-1, 0, 1]
    #     if get_elevation_arrays(s3_path(lat + lat_offset, lon + lon_offset)) is not None
    # ]
    # if len(neighbor_shapes) == 9 and len(set(neighbor_shapes)) == 1:
    #     arrays = np.concatenate(
    #         [
    #             np.concatenate(
    #                 [
    #                     get_elevation_arrays(
    #                         s3_path(lat + lat_offset, lon + lon_offset)
    #                     )
    #                     for lon_offset in [-1, 0, 1]
    #                 ],
    #                 axis=2,
    #             )
    #             for lat_offset in [1, 0, -1]
    #         ],
    #         axis=1,
    #     )
    lat_labels = arrays[1, :, 0]
    lon_labels = arrays[2, 0, :]

    return RegularGridInterpolator(
        (lat_labels, lon_labels), arrays[0], bounds_error=False, fill_value=None
    )


def get_elevation(lat: float, lon: float) -> float:
    interpolator = _get_interpolator(math.floor(lat), math.floor(lon))
    if interpolator is not None:
        return float(interpolator((lat, lon)))
    else:
        return 0.0
