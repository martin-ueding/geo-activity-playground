import functools

import altair as alt
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository


class SummaryController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self) -> dict:
        return {
            "distance_heatmap_meta_plot": distance_heatmap_meta_plot(
                self._repository.meta
            ),
            "year_on_year_distance_meta_plot": year_on_year_distance_meta_plot(
                self._repository.meta
            ),
        }


def distance_heatmap_meta_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta)
        .mark_rect()
        .encode(
            alt.X("date(start):O", title="Day of month"),
            alt.Y(
                "yearmonth(start):O",
                scale=alt.Scale(reverse=True),
                title="Year and month",
            ),
            alt.Color("sum(distance)", scale=alt.Scale(scheme="viridis")),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip("sum(distance)", format=".1f", title="Total distance / km"),
                alt.Tooltip("count(distance)", title="Number of activities"),
            ],
        )
        .to_json(format="vega")
    )


def year_on_year_distance_meta_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Year on Year Distance")
        .mark_bar()
        .encode(
            alt.X("month(start)"),
            alt.Y("sum(distance)"),
            alt.Color("kind", scale=alt.Scale(scheme="category10"), title="Kind"),
        )
        .facet(facet="year(start):O", columns=4)
        .to_json(format="vega")
    )
