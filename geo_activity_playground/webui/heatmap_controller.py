import functools
import io
import logging
import threading

import matplotlib
import matplotlib.pylab as pl
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageDraw

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import build_heatmap_tile
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import geo_bounds_from_tile_bounds
from geo_activity_playground.core.heatmap import get_all_points
from geo_activity_playground.core.heatmap import TileBounds
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.core.tiles import latlon_to_xy


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

    def render_tile(self, x: int, y: int, z: int) -> bytes:
        with self._mutex:
            all_points = get_all_points(self._repository)

        tile_bounds = TileBounds(z, x, x + 1, y, y + 1)
        geo_bounds = geo_bounds_from_tile_bounds(tile_bounds)

        logger.info(f"Filtering relevant points for {x}/{y} at {z} …")
        relevant_points = all_points.loc[
            (geo_bounds.lat_min <= all_points["latitude"])
            & (all_points["latitude"] <= geo_bounds.lat_max)
            & (geo_bounds.lon_min <= all_points["longitude"])
            & (all_points["longitude"] <= geo_bounds.lon_max)
        ].copy()

        tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
        tile_counts = np.zeros(tile_pixels, dtype=np.int32)
        for index, group in relevant_points.groupby("activity_id"):
            xy_pixels = (
                np.array([group["x"] * 2**z - x, group["y"] * 2**z - y]).T
                * OSM_TILE_SIZE
            )
            im = Image.new("L", tile_pixels)
            draw = ImageDraw.Draw(im)
            pixels = list(map(int, xy_pixels.flatten()))
            draw.line(pixels, fill=1, width=max(3, 6 * (z - 17)))
            aim = np.array(im)
            tile_counts += aim
        tile_counts = np.sqrt(tile_counts) / 5
        tile_counts[tile_counts > 1.0] = 1.0

        cmap = pl.get_cmap("hot")
        data_color = cmap(tile_counts)
        data_color[data_color == cmap(0.0)] = 0.0  # remove background color

        map_tile = np.array(get_tile(z, x, y)) / 255
        map_tile = convert_to_grayscale(map_tile)
        map_tile = 1.0 - map_tile  # invert colors
        for c in range(3):
            map_tile[:, :, c] = (1.0 - data_color[:, :, c]) * map_tile[
                :, :, c
            ] + data_color[:, :, c]

        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return bytes(f.getbuffer())
