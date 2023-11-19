import functools

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.explorer.grid_file import get_explored_geojson
from geo_activity_playground.explorer.grid_file import get_three_color_tiles


class ExplorerController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self) -> dict:
        explored_geojson = get_three_color_tiles(self._repository)
        return {"explored_geojson": explored_geojson}
