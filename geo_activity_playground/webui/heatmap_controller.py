import functools
import io
import logging

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import get_all_points
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon


logger = logging.getLogger(__name__)


class HeatmapController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository
        self._all_points = pd.DataFrame()

    @functools.cache
    def render(self) -> dict:
        self._all_points = get_all_points(self._repository)
        print(self._all_points)
        medians = self._all_points.median()
        return {
            "center": {
                "latitude": medians["latitude"],
                "longitude": medians["longitude"],
            }
        }

    def render_tile(self, x: int, y: int, z: int) -> bytes:
        lat_min, lon_min = get_tile_upper_left_lat_lon(x, y, z)
        lat_max, lon_max = get_tile_upper_left_lat_lon(x + 1, y + 1, z)

        logger.info(f"Filtering relevant points for {x}/{y} at {z} …")
        relevant_points = self._all_points.loc[
            (lat_min <= self._all_points["latitude"])
            & (self._all_points["latitude"] <= lat_max)
            & (lon_min <= self._all_points["longitude"])
            & (self._all_points["longitude"] <= lon_max)
        ]

        map_tile = get_tile(z, x, y)
        f = io.BytesIO()
        map_tile.save(f, format="png")
        return bytes(f.getbuffer())
