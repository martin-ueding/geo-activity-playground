import datetime

import altair as alt
import numpy as np
import pandas as pd
from flask import Blueprint
from flask import render_template
from flask import request

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.meta_search import apply_search_query
from geo_activity_playground.webui.search_util import search_query_from_form
from geo_activity_playground.webui.search_util import SearchQueryHistory


def make_elevation_eddington_blueprint(
    repository: ActivityRepository, search_query_history: SearchQueryHistory
) -> Blueprint:
    blueprint = Blueprint("elevation_eddington", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = (
            apply_search_query(repository.meta, query)
            .dropna(subset=["start", "elevation_gain"])
            .copy()
        )

        activities["year"] = [start.year for start in activities["start"]]
        activities["date"] = [start.date() for start in activities["start"]]
        activities["isoyear"] = [
            start.isocalendar().year for start in activities["start"]
        ]
        activities["isoweek"] = [
            start.isocalendar().week for start in activities["start"]
        ]

        en_per_day, eddington_df_per_day = _get_distances_per_group(
            activities.groupby("date")
        )
        en_per_week, eddington_df_per_week = _get_distances_per_group(
            activities.groupby(["isoyear", "isoweek"])
        )

        return render_template(
            "elevation_eddington/index.html.j2",
            eddington_number=en_per_day,
            logarithmic_plot=_make_eddington_plot(
                eddington_df_per_day, en_per_day, "Days"
            ),
            eddington_per_week=en_per_week,
            eddington_per_week_plot=_make_eddington_plot(
                eddington_df_per_week, en_per_week, "Weeks"
            ),
            eddington_table=eddington_df_per_day.loc[
                (eddington_df_per_day["elevation_gain"] > en_per_day)
                & (eddington_df_per_day["elevation_gain"] <= en_per_day + 10)
            ].to_dict(orient="records"),
            eddington_table_weeks=eddington_df_per_week.loc[
                (eddington_df_per_week["elevation_gain"] > en_per_week)
                & (eddington_df_per_week["elevation_gain"] <= en_per_week + 10)
            ].to_dict(orient="records"),
            query=query.to_jinja(),
            yearly_eddington=_get_yearly_eddington(activities),
            eddington_number_history_plot=_get_eddington_number_history(activities),
        )

    return blueprint


def _get_distances_per_group(grouped) -> tuple[int, pd.DataFrame]:
    sum_per_group = grouped.apply(
        lambda group: int(sum(group["elevation_gain"])), include_groups=False
    )
    counts = dict(zip(*np.unique(sorted(sum_per_group), return_counts=True)))
    eddington = pd.DataFrame(
        {"elevation_gain": d, "count": counts.get(d, 0)}
        for d in range(max(counts.keys()) + 1)
    )
    eddington["total"] = eddington["count"][::-1].cumsum()[::-1]
    en = eddington.loc[eddington["total"] >= eddington["elevation_gain"]][
        "elevation_gain"
    ].iloc[-1]
    eddington["missing"] = eddington["elevation_gain"] - eddington["total"]
    return en, eddington


def _make_eddington_plot(eddington_df: pd.DataFrame, en: int, interval: str) -> dict:
    x = list(range(1, max(eddington_df["elevation_gain"]) + 1))
    return (
        (
            (
                alt.Chart(
                    eddington_df,
                    height=500,
                    width=800,
                    title=f"Elevation Eddington Number {en}",
                )
                .mark_area(interpolate="step")
                .encode(
                    alt.X(
                        "elevation_gain",
                        scale=alt.Scale(domainMin=0),
                        title="Elevation Gain",
                    ),
                    alt.Y(
                        "total",
                        scale=alt.Scale(domainMax=en + 10),
                        title=f"{interval} exceeding distance",
                    ),
                    [
                        alt.Tooltip("elevation_gain", title="Elevation Gain"),
                        alt.Tooltip("total", title=f"{interval} exceeding distance"),
                        alt.Tooltip("missing", title=f"{interval} missing for next"),
                    ],
                )
            )
            + (
                alt.Chart(pd.DataFrame({"elevation_gain": x, "total": x}))
                .mark_line(color="red")
                .encode(alt.X("elevation_gain"), alt.Y("total"))
            )
        )
        .interactive(bind_x=False)
        .to_json(format="vega")
    )


def _get_eddington_number(distances: pd.Series) -> int:
    if len(distances) == 1:
        if distances.iloc[0] >= 1:
            return 1
        else:
            0

    sorted_distances = sorted(distances, reverse=True)
    for en, distance in enumerate(sorted_distances, 1):
        if distance < en:
            return en - 1


def _get_yearly_eddington(meta: pd.DataFrame) -> dict[int, int]:
    meta = meta.dropna(subset=["start", "elevation_gain"]).copy()
    meta["year"] = [start.year for start in meta["start"]]
    meta["date"] = [start.date() for start in meta["start"]]

    yearly_eddington = meta.groupby("year").apply(
        lambda group: _get_eddington_number(
            group.groupby("date").apply(
                lambda group2: int(group2["elevation_gain"].sum()), include_groups=False
            )
        ),
        include_groups=False,
    )
    return yearly_eddington.to_dict()


def _get_eddington_number_history(meta: pd.DataFrame) -> dict:

    daily_distances = meta.groupby("date").apply(
        lambda group2: int(group2["elevation_gain"].sum()), include_groups=False
    )

    eddington_number_history = {"date": [], "eddington_number": []}
    top_days = []
    for date, distance in daily_distances.items():
        if len(top_days) == 0:
            top_days.append(distance)
        else:
            if distance >= top_days[0]:
                top_days.append(distance)
                top_days.sort()
        while top_days[0] < len(top_days):
            top_days.pop(0)
        eddington_number_history["date"].append(
            datetime.datetime.combine(date, datetime.datetime.min.time())
        )
        eddington_number_history["eddington_number"].append(len(top_days))
    history = pd.DataFrame(eddington_number_history)

    return (
        alt.Chart(history)
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("date", title="Date"),
            alt.Y("eddington_number", title="Eddington number"),
        )
    ).to_json(format="vega")
