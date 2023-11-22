import functools

import altair as alt
import geojson
import pandas as pd

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

        result = {
            "activity": activity,
            "line_json": line_json,
            "distance_time_plot": distance_time_plot(time_series),
        }
        if "altitude" in time_series.columns:
            result["altitude_time_plot"] = altitude_time_plot(time_series)
        if "heartrate" in time_series.columns:
            result["heartrate_time_plot"] = heartrate_time_plot(time_series)
        return result


def distance_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Distance")
        .mark_line()
        .encode(alt.X("time", title="Time"), alt.Y("distance", title="Distance / km"))
        .interactive()
        .to_json(format="vega")
    )


def altitude_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Altitude")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("altitude", scale=alt.Scale(zero=False), title="Altitude / m"),
        )
        .interactive()
        .to_json(format="vega")
    )


def heartrate_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Heart Rate")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("heartrate", scale=alt.Scale(zero=False), title="Heart rate"),
        )
        .interactive()
        .to_json(format="vega")
    )
