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
from geo_activity_playground.core.heatmap import compute_activities_per_tile
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import geo_bounds_from_tile_bounds
from geo_activity_playground.core.heatmap import get_all_points
from geo_activity_playground.core.heatmap import TileBounds
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.core.tiles import latlon_to_xy
from geo_activity_playground.explorer.clusters import bounding_box_for_biggest_cluster
from geo_activity_playground.explorer.clusters import get_explorer_cluster_evolution
from geo_activity_playground.explorer.converters import get_tile_history


logger = logging.getLogger(__name__)


OSM_TILE_SIZE = 256  # OSM tile size in pixel


class HeatmapController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository
        self._all_points = pd.DataFrame()
        self._mutex = threading.Lock()

    @functools.cache
    def render(self) -> dict:
        zoom = 14
        tiles = get_tile_history(self._repository, zoom)
        medians = tiles.median()
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )
        cluster_state = get_explorer_cluster_evolution(zoom)
        return {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": bounding_box_for_biggest_cluster(
                    cluster_state.clusters.values(), zoom
                )
                if len(cluster_state.memberships) > 0
                else {},
            }
        }

    def render_tile(self, x: int, y: int, z: int) -> bytes:
        with self._mutex:
            activities_per_tile = compute_activities_per_tile(self._repository)
        tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
        tile_counts = np.zeros(tile_pixels, dtype=np.int32)
        for activity_id in activities_per_tile[z].get((x, y), set()):
            time_series = self._repository.get_time_series(activity_id)
            ts_x, ts_y = compute_tile_float(
                time_series["latitude"], time_series["longitude"], z
            )
            xy_pixels = np.array([ts_x - x, ts_y - y]).T * OSM_TILE_SIZE
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
