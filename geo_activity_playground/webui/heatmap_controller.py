import io

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tiles import get_tile


class HeatmapController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    def render(self) -> dict:
        return {}

    def render_tile(self, x: int, y: int, z: int) -> bytes:
        tile = get_tile(z, x, y)
        f = io.BytesIO()
        tile.save(f, format="png")
        return bytes(f.getbuffer())
