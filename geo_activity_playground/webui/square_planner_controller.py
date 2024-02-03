import pickle

import geojson

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.explorer.grid_file import make_explorer_rectangle
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

        return {"explored_geojson": {}, "square_geojson": square_geojson}
