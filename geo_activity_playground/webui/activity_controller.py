import functools

import altair as alt
import geojson

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import make_geojson_from_time_series


class ActivityController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.lru_cache()
    def render_activity(self, id: int) -> dict:
        activity = self._repository.get_activity_by_id(id)

        time_series = self._repository.get_time_series(id)
        line_json = make_geojson_from_time_series(time_series)

        return {
            "activity": activity,
            "line_json": line_json,
        }
