import functools
import io

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import get_all_points
from geo_activity_playground.core.tiles import get_tile


class HeatmapController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

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
        tile = get_tile(z, x, y)
        f = io.BytesIO()
        tile.save(f, format="png")
        return bytes(f.getbuffer())
