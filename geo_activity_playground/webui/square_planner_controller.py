import functools
import pickle

import geojson

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.explorer.grid_file import make_explorer_rectangle
from geo_activity_playground.explorer.grid_file import make_explorer_tile
from geo_activity_playground.explorer.tile_visits import TILE_VISITS_PATH


class SquarePlannerController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

        with open(TILE_VISITS_PATH, "rb") as f:
            self._tile_visits = pickle.load(f)

    def render(self, zoom: int, square_x: int, square_y: int, square_size: int) -> dict:
        square_geojson = geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_rectangle(
                        square_x,
                        square_y,
                        square_x + square_size,
                        square_y + square_size,
                        zoom,
                    )
                ]
            )
        )

        missing_geojson = geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_tile(
                        tile_x,
                        tile_y,
                        {},
                        zoom,
                    )
                    for tile_x in range(square_x, square_x + square_size)
                    for tile_y in range(square_y, square_y + square_size)
                    if (tile_x, tile_y) not in self._get_explored_tiles(zoom)
                ]
            )
        )

        return {
            "explored_geojson": self._get_explored_geojson(zoom),
            "missing_geojson": missing_geojson,
            "square_geojson": square_geojson,
        }

    @functools.cache
    def _get_explored_tiles(self, zoom: int) -> set[tuple[int, int]]:
        return set(self._tile_visits[zoom].keys())

    @functools.cache
    def _get_explored_geojson(self, zoom: int) -> str:
        return geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_tile(
                        tile_x,
                        tile_y,
                        {},
                        zoom,
                    )
                    for tile_x, tile_y in self._tile_visits[zoom].keys()
                ]
            )
        )
