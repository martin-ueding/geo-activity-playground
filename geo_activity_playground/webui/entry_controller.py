import datetime
import functools
import itertools

import altair as alt
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import make_geojson_from_time_series


class EntryController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self) -> dict:
        result = {
            "distance_last_30_days_plot": self.distance_last_30_days_meta_plot(),
            "latest_activities": [],
        }

        for activity in itertools.islice(self._repository.iter_activities(), 15):
            time_series = self._repository.get_time_series(activity.id)
            result["latest_activities"].append(
                {
                    "line_geojson": make_geojson_from_time_series(time_series),
                    "activity": activity,
                }
            )
        return result

    def distance_last_30_days_meta_plot(self) -> str:
        meta = self._repository.meta
        before_30_days = pd.to_datetime(
            datetime.datetime.utcnow() - datetime.timedelta(days=31), utc=True
        )
        print(repr(meta["start"].iloc[0]))
        print(repr(before_30_days))
        return (
            alt.Chart(
                meta.loc[meta["start"] > before_30_days],
                width=700,
                height=200,
                title="Distance per day",
            )
            .mark_bar()
            .encode(
                alt.X("yearmonthdate(start)", title="Date"),
                alt.Y("sum(distance)", title="Distance / km"),
                alt.Color("kind", scale=alt.Scale(scheme="category10"), title="Kind"),
                [alt.Tooltip("yearmonthdate(start)")],
            )
            .to_json(format="vega")
        )
