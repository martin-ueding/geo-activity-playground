import pickle

import geojson

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.explorer.grid_file import make_explorer_rectangle
from geo_activity_playground.explorer.grid_file import make_explorer_tile
from geo_activity_playground.explorer.grid_file import make_grid_file_geojson
from geo_activity_playground.explorer.grid_file import make_grid_file_gpx
from geo_activity_playground.explorer.grid_file import make_grid_points
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor


class SquarePlannerController:
    def __init__(
        self, repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
    ) -> None:
        self._repository = repository
        self._tile_visit_accessor = tile_visit_accessor

        self._tile_visits = self._tile_visit_accessor.tile_state["tile_visits"]

    def action_planner(
        self, zoom: int, square_x: int, square_y: int, square_size: int
    ) -> dict:
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
            "zoom": zoom,
            "square_x": square_x,
            "square_y": square_y,
            "square_size": square_size,
        }

    def export_missing_tiles(
        self, zoom: int, square_x: int, square_y: int, square_size: int, suffix: str
    ) -> str:
        points = make_grid_points(
            (
                (tile_x, tile_y)
                for tile_x in range(square_x, square_x + square_size)
                for tile_y in range(square_y, square_y + square_size)
                if (tile_x, tile_y) not in self._get_explored_tiles(zoom)
            ),
            zoom,
        )
        if suffix == "geojson":
            return make_grid_file_geojson(points)
        elif suffix == "gpx":
            return make_grid_file_gpx(points)
        else:
            raise RuntimeError(f"Unsupported suffix {suffix}.")

    def _get_explored_tiles(self, zoom: int) -> set[tuple[int, int]]:
        return set(self._tile_visits[zoom].keys())

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
