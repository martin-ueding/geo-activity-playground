import functools
import io
import logging
import pathlib
import pickle
import threading

import matplotlib
import matplotlib.pylab as pl
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageDraw

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import GeoBounds
from geo_activity_playground.core.heatmap import get_sensible_zoom_level
from geo_activity_playground.core.tasks import work_tracker
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.explorer.tile_visits import TILE_EVOLUTION_STATES_PATH
from geo_activity_playground.explorer.tile_visits import TILE_HISTORIES_PATH
from geo_activity_playground.explorer.tile_visits import TILE_VISITS_PATH
from geo_activity_playground.webui.explorer_controller import (
    bounding_box_for_biggest_cluster,
)


logger = logging.getLogger(__name__)


OSM_TILE_SIZE = 256  # OSM tile size in pixel


class HeatmapController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository
        self._all_points = pd.DataFrame()

        with open(TILE_HISTORIES_PATH, "rb") as f:
            self.tile_histories = pickle.load(f)
        with open(TILE_EVOLUTION_STATES_PATH, "rb") as f:
            self.tile_evolution_states = pickle.load(f)
        with open(TILE_VISITS_PATH, "rb") as f:
            self.tile_visits = pickle.load(f)

    @functools.cache
    def render(self) -> dict:
        zoom = 14
        tiles = self.tile_histories[zoom]
        medians = tiles.median()
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )
        cluster_state = self.tile_evolution_states[zoom]
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

    def _render_tile_image(self, x: int, y: int, z: int) -> np.ndarray:
        tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
        tile_count_cache_path = pathlib.Path(f"Cache/Heatmap/{z}/{x}/{y}.npy")
        if tile_count_cache_path.exists():
            tile_counts = np.load(tile_count_cache_path)
        else:
            tile_counts = np.zeros(tile_pixels, dtype=np.int32)
        tile_count_cache_path.parent.mkdir(parents=True, exist_ok=True)
        activity_ids = self.tile_visits[z].get((x, y), {}).get("activity_ids", set())
        if activity_ids:
            with work_tracker(
                tile_count_cache_path.with_suffix(".json")
            ) as parsed_activities:
                for activity_id in activity_ids:
                    if activity_id in parsed_activities:
                        continue
                    parsed_activities.add(activity_id)
                    time_series = self._repository.get_time_series(activity_id)
                    for _, group in time_series.groupby("segment_id"):
                        xy_pixels = (
                            np.array(
                                [group["x"] * 2**z - x, group["y"] * 2**z - y]
                            ).T
                            * OSM_TILE_SIZE
                        )
                        im = Image.new("L", tile_pixels)
                        draw = ImageDraw.Draw(im)
                        pixels = list(map(int, xy_pixels.flatten()))
                        draw.line(pixels, fill=1, width=max(3, 6 * (z - 17)))
                        aim = np.array(im)
                        tile_counts += aim
            np.save(tile_count_cache_path, tile_counts)
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
        return map_tile

    def render_tile(self, x: int, y: int, z: int) -> bytes:
        f = io.BytesIO()
        pl.imsave(f, self._render_tile_image(x, y, z), format="png")
        return bytes(f.getbuffer())

    def download_heatmap(self, north, east, south, west) -> bytes:
        geo_bounds = GeoBounds(south, west, north, east)
        tile_bounds = get_sensible_zoom_level(geo_bounds, (4000, 4000))

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
                ] = self._render_tile_image(x, y, tile_bounds.zoom)

        f = io.BytesIO()
        pl.imsave(f, background, format="png")
        return bytes(f.getbuffer())
