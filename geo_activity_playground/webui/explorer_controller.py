import functools

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.explorer.converters import get_tile_history
from geo_activity_playground.explorer.grid_file import get_border_tiles
from geo_activity_playground.explorer.grid_file import get_explored_geojson
from geo_activity_playground.explorer.grid_file import get_explored_tiles
from geo_activity_playground.explorer.grid_file import get_three_color_tiles
from geo_activity_playground.explorer.grid_file import make_grid_file_geojson
from geo_activity_playground.explorer.grid_file import make_grid_file_gpx


class ExplorerController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self, zoom: int) -> dict:
        tiles = get_tile_history(self._repository, zoom)
        medians = tiles.median()
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )

        explored = get_three_color_tiles(tiles, self._repository, zoom)

        points = get_border_tiles(tiles, zoom)
        missing_tiles_geojson = make_grid_file_geojson(points, "missing_tiles")
        make_grid_file_gpx(points, "missing_tiles")

        points = get_explored_tiles(tiles, zoom)
        explored_tiles_geojson = make_grid_file_geojson(points, "explored")
        make_grid_file_gpx(points, "explored")

        return {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
            },
            "explored": explored,
            "missing_tiles_geojson": missing_tiles_geojson,
        }
