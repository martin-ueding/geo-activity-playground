import collections
import datetime

import altair as alt
import pandas as pd
from flask import render_template
from flask import Response

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import make_geojson_from_time_series
from geo_activity_playground.core.config import Config
from geo_activity_playground.webui.interfaces import MyView
from geo_activity_playground.webui.plot_util import make_kind_scale


class EntryView(MyView):
    def __init__(self, repository: ActivityRepository, config: Config) -> None:
        self._repository = repository
        self._config = config

    def register(self, app):
        app.add_url_rule("/", "index", self.dispatch)

    def dispatch(self) -> Response:
        context = {"latest_activities": []}

        if len(self._repository):
            kind_scale = make_kind_scale(self._repository.meta, self._config)
            context["distance_last_30_days_plot"] = _distance_last_30_days_meta_plot(
                self._repository.meta, kind_scale
            )
            context["elevation_gain_last_30_days_plot"] = (
                _elevation_gain_last_30_days_meta_plot(
                    self._repository.meta, kind_scale
                )
            )

            meta = self._repository.meta.copy()
            meta["date"] = meta["start"].dt.date

            context["latest_activities"] = collections.defaultdict(list)
            for date, activity_meta in list(meta.groupby("date"))[:-30:-1]:
                for index, activity in activity_meta.iterrows():
                    time_series = self._repository.get_time_series(activity["id"])
                    context["latest_activities"][date].append(
                        {
                            "activity": activity,
                            "line_geojson": make_geojson_from_time_series(time_series),
                        }
                    )
        return render_template("home.html.j2", **context)


def _distance_last_30_days_meta_plot(meta: pd.DataFrame, kind_scale: alt.Scale) -> str:
    before_30_days = pd.to_datetime(
        datetime.datetime.now() - datetime.timedelta(days=31)
    )
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
            alt.Y("sum(distance_km)", title="Distance / km"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip("sum(distance_km)", format=".1f", title="Distance / km"),
            ],
        )
        .to_json(format="vega")
    )


def _elevation_gain_last_30_days_meta_plot(
    meta: pd.DataFrame, kind_scale: alt.Scale
) -> str:
    before_30_days = pd.to_datetime(
        datetime.datetime.now() - datetime.timedelta(days=31)
    )
    return (
        alt.Chart(
            meta.loc[meta["start"] > before_30_days],
            width=700,
            height=200,
            title="Elevation gain per day",
        )
        .mark_bar()
        .encode(
            alt.X("yearmonthdate(start)", title="Date"),
            alt.Y("sum(elevation_gain)", title="Elevation gain / m"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip(
                    "sum(elevation_gain)", format=".0f", title="Elevation gain / "
                ),
            ],
        )
        .to_json(format="vega")
    )
