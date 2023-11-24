import functools
import io
import logging
import threading

import matplotlib
import matplotlib.pylab as pl
import numpy as np
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import get_all_points
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.core.tiles import latlon_to_xy
from geo_activity_playground.heatmap import gaussian_filter


logger = logging.getLogger(__name__)


OSM_TILE_SIZE = 256  # OSM tile size in pixel


class HeatmapController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository
        self._all_points = pd.DataFrame()
        self._mutex = threading.Lock()

    @functools.cache
    def render(self) -> dict:
        all_points = get_all_points(self._repository)
        medians = all_points.median()
        return {
            "center": {
                "latitude": medians["latitude"],
                "longitude": medians["longitude"],
            }
        }

    @functools.cache
    def compute_xy(self, z: int) -> pd.DataFrame:
        points = get_all_points(self._repository)
        x, y = latlon_to_xy(points["latitude"], points["longitude"], z)
        self._xy = pd.DataFrame(
            {"x": x * OSM_TILE_SIZE, "y": y * OSM_TILE_SIZE}, dtype="int"
        )
        return self._xy

    @functools.cache
    def compute_hist(self, z: int, num_activities: int) -> np.ndarray:
        counts = self._xy.groupby(["x", "y"]).apply(lambda group: len(group))
        # counts, counts2 = np.unique(counts, return_counts=True)
        # print(counts.tolist())
        # print(counts2.tolist())

        res_pixel = (
            156543.03 * np.cos(np.radians(50)) / (2.0**z)
        )  # from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames

        # trackpoint max accumulation per pixel = 1/5 (trackpoint/meter) * res_pixel (meter/pixel) * activities
        # (Strava records trackpoints every 5 meters in average for cycling activites)
        m = np.round((1.0 / 5.0) * res_pixel * num_activities)
        print(f"{m = }")
        counts.loc[counts > m] = m

        # equalize histogram and compute kernel density estimation
        data_hist, _ = np.histogram(counts, bins=int(m + 1))
        print(f"{data_hist = }")

        data_hist = np.cumsum(data_hist)
        normalized_histogram = data_hist / data_hist[-1]
        print(f"{normalized_histogram = }")
        return normalized_histogram

    def render_tile(self, x: int, y: int, z: int) -> bytes:
        with self._mutex:
            all_points = get_all_points(self._repository)
            # xy = self.compute_xy(z)
            # data_hist = self.compute_hist(z, len(self._repository.meta))

        lat_max, lon_min = get_tile_upper_left_lat_lon(x, y, z)
        lat_min, lon_max = get_tile_upper_left_lat_lon(x + 1, y + 1, z)

        logger.info(f"Filtering relevant points for {x}/{y} at {z} …")
        relevant_points = all_points.loc[
            (lat_min <= all_points["latitude"])
            & (all_points["latitude"] <= lat_max)
            & (lon_min <= all_points["longitude"])
            & (all_points["longitude"] <= lon_max)
        ]

        xy_data = latlon_to_xy(
            relevant_points["latitude"], relevant_points["longitude"], z
        )
        xy_data = np.array(xy_data).T

        x_tile_min, y_tile_max = map(int, latlon_to_xy(lat_min, lon_min, z))
        x_tile_max, y_tile_min = map(int, latlon_to_xy(lat_max, lon_max, z))
        xy_data = np.round((xy_data - [x_tile_min, y_tile_min]) * OSM_TILE_SIZE)
        sigma_pixel = 1
        data = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE))
        for j, i in xy_data.astype(int):
            data[
                i - sigma_pixel : i + sigma_pixel, j - sigma_pixel : j + sigma_pixel
            ] += 1.0

        res_pixel = (
            156543.03 * np.cos(np.radians(np.mean(all_points["latitude"]))) / (2.0**z)
        )  # from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames

        # trackpoint max accumulation per pixel = 1/5 (trackpoint/meter) * res_pixel (meter/pixel) * activities
        # (Strava records trackpoints every 5 meters in average for cycling activites)
        # m = len(data_hist) - 1
        # data[data > m] = m
        # data_hist[0] = 0

        # for i in range(data.shape[0]):
        #     for j in range(data.shape[1]):
        #         data[i, j] = m * data_hist[int(data[i, j])]  # histogram equalization

        # data = gaussian_filter(data, float(sigma_pixel))

        np.log(data, where=data > 0, out=data)
        data /= 6
        data_max = data.max()
        if data_max > 2:
            logger.warning(f"Maximum data in tile: {data_max}")
        data[data > 1.0] = 1.0

        # colorize
        cmap = matplotlib.colormaps["hot"]

        data_color = cmap(data)
        data_color[data_color == cmap(0.0)] = 0.0  # remove background color

        map_tile = np.array(get_tile(z, x, y)) / 255
        map_tile = np.sum(map_tile * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        map_tile = 1.0 - map_tile  # invert colors
        map_tile = np.dstack((map_tile, map_tile, map_tile))  # to rgb
        for c in range(3):
            map_tile[:, :, c] = (1.0 - data_color[:, :, c]) * map_tile[
                :, :, c
            ] + data_color[:, :, c]

        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return bytes(f.getbuffer())
