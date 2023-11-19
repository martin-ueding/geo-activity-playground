import functools

import altair as alt

from geo_activity_playground.core.activities import ActivityRepository


class ActivityController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.lru_cache()
    def render_activity(self, id: int) -> dict:
        activity = self._repository.get_activity_by_id(id)

        time_series = self._repository.get_time_series(id)
        activity_plot = (
            alt.Chart(time_series)
            .mark_line()
            .encode(alt.Latitude("latitude"), alt.Longitude("longitude"))
        ).to_json(format="vega")

        return {"activity": activity, "activity_plot": activity_plot}
