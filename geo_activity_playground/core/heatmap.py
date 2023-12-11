"""
This code is based on https://github.com/remisalmon/Strava-local-heatmap.
"""
import dataclasses
import functools
import logging
import pathlib

import matplotlib.pyplot as pl
import numpy as np
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import work_tracker
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon


logger = logging.getLogger(__name__)


@functools.cache
def get_all_points(repository: ActivityRepository) -> pd.DataFrame:
    logger.info("Gathering all points …")
    all_points_path = pathlib.Path("Cache/all-points.parquet")
    if all_points_path.exists():
        all_points = pd.read_parquet(all_points_path)
    else:
        all_points = pd.DataFrame()
    new_shards = []
    with work_tracker(pathlib.Path("Cache/all-points-task.json")) as tracker:
        for activity in repository.iter_activities():
            if activity.id in tracker:
                continue
            tracker.add(activity.id)

            logger.info(f"Parsing points from {activity.id} …")
            time_series = repository.get_time_series(activity.id)
            if len(time_series) == 0 or "latitude" not in time_series.columns:
                continue
            shard = time_series[["latitude", "longitude"]].copy()
            shard["activity_id"] = activity.id
            new_shards.append(shard)
    logger.info("Concatenating shards …")
    all_points = pd.concat([all_points] + new_shards)
    all_points.to_parquet(all_points_path)
    return all_points


@dataclasses.dataclass
class GeoBounds:
    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float


def get_bounds(lat_lon_data: np.array) -> GeoBounds:
    return GeoBounds(*np.min(lat_lon_data, axis=0), *np.max(lat_lon_data, axis=0))


def add_margin(lower: float, upper: float) -> tuple[float, float]:
    spread = upper - lower
    margin = spread / 20
    return max(0, lower - margin), upper + margin


def add_margin_to_geo_bounds(bounds: GeoBounds) -> GeoBounds:
    lat_min, lat_max = add_margin(bounds.lat_min, bounds.lat_max)
    lon_min, lon_max = add_margin(bounds.lon_min, bounds.lon_max)
    return GeoBounds(lat_min, lon_min, lat_max, lon_max)


OSM_TILE_SIZE = 256  # OSM tile size in pixel
OSM_MAX_ZOOM = 19  # OSM maximum zoom level
MAX_TILE_COUNT = 2000  # maximum number of tiles to download


@dataclasses.dataclass
class TileBounds:
    zoom: int
    x_tile_min: int
    x_tile_max: int
    y_tile_min: int
    y_tile_max: int

    @property
    def shape(self) -> tuple[int, int]:
        return (
            (self.y_tile_max - self.y_tile_min) * OSM_TILE_SIZE,
            (self.x_tile_max - self.x_tile_min) * OSM_TILE_SIZE,
        )


def geo_bounds_from_tile_bounds(tile_bounds: TileBounds) -> GeoBounds:
    lat_max, lon_min = get_tile_upper_left_lat_lon(
        tile_bounds.x_tile_min, tile_bounds.y_tile_min, tile_bounds.zoom
    )
    lat_min, lon_max = get_tile_upper_left_lat_lon(
        tile_bounds.x_tile_max, tile_bounds.y_tile_max, tile_bounds.zoom
    )
    return GeoBounds(lat_min, lon_min, lat_max, lon_max)


def get_sensible_zoom_level(
    bounds: GeoBounds, picture_size: tuple[int, int]
) -> TileBounds:
    zoom = OSM_MAX_ZOOM

    while True:
        x_tile_min, y_tile_max = map(
            int, compute_tile_float(bounds.lat_min, bounds.lon_min, zoom)
        )
        x_tile_max, y_tile_min = map(
            int, compute_tile_float(bounds.lat_max, bounds.lon_max, zoom)
        )

        x_tile_max += 1
        y_tile_max += 1

        if (x_tile_max - x_tile_min) * OSM_TILE_SIZE <= picture_size[0] and (
            y_tile_max - y_tile_min
        ) * OSM_TILE_SIZE <= picture_size[1]:
            break

        zoom -= 1

    tile_count = (x_tile_max - x_tile_min) * (y_tile_max - y_tile_min)

    if tile_count > MAX_TILE_COUNT:
        raise RuntimeError("Zoom value too high, too many tiles to download")

    return TileBounds(
        zoom=zoom,
        x_tile_min=x_tile_min,
        x_tile_max=x_tile_max,
        y_tile_min=y_tile_min,
        y_tile_max=y_tile_max,
    )


def build_map_from_tiles(tile_bounds: TileBounds) -> np.array:
    background = np.zeros((*tile_bounds.shape, 3))

    for x in range(tile_bounds.x_tile_min, tile_bounds.x_tile_max):
        for y in range(tile_bounds.y_tile_min, tile_bounds.y_tile_max):
            tile = np.array(get_tile(tile_bounds.zoom, x, y)) / 255

            i = y - tile_bounds.y_tile_min
            j = x - tile_bounds.x_tile_min

            background[
                i * OSM_TILE_SIZE : (i + 1) * OSM_TILE_SIZE,
                j * OSM_TILE_SIZE : (j + 1) * OSM_TILE_SIZE,
                :,
            ] = tile[:, :, :3]

    return background


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
    image = np.dstack((image, image, image))
    return image


def crop_image_to_bounds(
    image: np.ndarray, geo_bounds: GeoBounds, tile_bounds: TileBounds
) -> np.ndarray:
    min_x, min_y = compute_tile_float(
        geo_bounds.lat_max, geo_bounds.lon_min, tile_bounds.zoom
    )
    max_x, max_y = compute_tile_float(
        geo_bounds.lat_min, geo_bounds.lon_max, tile_bounds.zoom
    )
    min_x = int((min_x - tile_bounds.x_tile_min) * OSM_TILE_SIZE)
    min_y = int((min_y - tile_bounds.y_tile_min) * OSM_TILE_SIZE)
    max_x = int((max_x - tile_bounds.x_tile_min) * OSM_TILE_SIZE)
    max_y = int((max_y - tile_bounds.y_tile_min) * OSM_TILE_SIZE)
    image = image[min_y:max_y, min_x:max_x, :]
    return image


def gaussian_filter(image, sigma):
    # returns image filtered with a gaussian function of variance sigma**2
    #
    # input: image = numpy.ndarray
    #        sigma = float
    # output: image = numpy.ndarray

    i, j = np.meshgrid(
        np.arange(image.shape[0]), np.arange(image.shape[1]), indexing="ij"
    )

    mu = (int(image.shape[0] / 2.0), int(image.shape[1] / 2.0))

    gaussian = (
        1.0
        / (2.0 * np.pi * sigma * sigma)
        * np.exp(-0.5 * (((i - mu[0]) / sigma) ** 2 + ((j - mu[1]) / sigma) ** 2))
    )

    gaussian = np.roll(gaussian, (-mu[0], -mu[1]), axis=(0, 1))

    image_fft = np.fft.rfft2(image)
    gaussian_fft = np.fft.rfft2(gaussian)

    image = np.fft.irfft2(image_fft * gaussian_fft)

    return image


def build_heatmap_image(
    lat_lon_data: np.ndarray, num_activities: int, tile_bounds: TileBounds
) -> np.ndarray:
    # fill trackpoints
    sigma_pixel = 1

    data = np.zeros(tile_bounds.shape)

    xy_data = compute_tile_float(
        lat_lon_data[:, 0], lat_lon_data[:, 1], tile_bounds.zoom
    )
    xy_data = np.array(xy_data).T
    xy_data = np.round(
        (xy_data - [tile_bounds.x_tile_min, tile_bounds.y_tile_min]) * OSM_TILE_SIZE
    )  # to supertile coordinates

    for j, i in xy_data.astype(int):
        data[
            i - sigma_pixel : i + sigma_pixel, j - sigma_pixel : j + sigma_pixel
        ] += 1.0

    res_pixel = (
        156543.03
        * np.cos(np.radians(np.mean(lat_lon_data[:, 0])))
        / (2.0**tile_bounds.zoom)
    )  # from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames

    # trackpoint max accumulation per pixel = 1/5 (trackpoint/meter) * res_pixel (meter/pixel) * activities
    # (Strava records trackpoints every 5 meters in average for cycling activites)
    m = np.round((1.0 / 5.0) * res_pixel * num_activities)

    data[data > m] = m

    # equalize histogram and compute kernel density estimation
    data_hist, _ = np.histogram(data, bins=int(m + 1))

    data_hist = np.cumsum(data_hist) / data.size  # normalized cumulated histogram

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            data[i, j] = m * data_hist[int(data[i, j])]  # histogram equalization

    data = gaussian_filter(
        data, float(sigma_pixel)
    )  # kernel density estimation with normal kernel

    data = (data - data.min()) / (data.max() - data.min())  # normalize to [0,1]

    # colorize
    cmap = pl.get_cmap("hot")

    data_color = cmap(data)
    data_color[data_color == cmap(0.0)] = 0.0  # remove background color
    return data_color
