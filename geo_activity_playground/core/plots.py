import datetime

import altair as alt
import numpy as np
import pandas as pd

alt.data_transformers.enable("vegafusion")


def activity_track_plot(time_series: pd.DataFrame) -> str:
    chart = (
        alt.Chart(time_series)
        .mark_line()
        .encode(alt.Latitude("latitude"), alt.Longitude("longitude"))
    )
    return chart.to_json(format="vega")


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


def distance_last_30_days_meta_plot(meta: pd.DataFrame) -> str:
    before_30_days = pd.to_datetime(
        datetime.datetime.utcnow() - datetime.timedelta(days=31), utc=True
    )
    return (
        alt.Chart(
            meta.loc[meta["start"] > before_30_days],
            width=800,
            height=300,
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


meta_plots = {
    "distance-heatmap": distance_heatmap_meta_plot,
    "distance-last-30-days": distance_last_30_days_meta_plot,
    "year-on-year-distance": year_on_year_distance_meta_plot,
}
