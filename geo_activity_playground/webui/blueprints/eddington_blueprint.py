import datetime

import altair as alt
import numpy as np
import pandas as pd
from flask import Blueprint
from flask import render_template
from flask import request

from ...core.activities import ActivityRepository
from ...core.meta_search import apply_search_query
from ..search_util import search_query_from_form
from ..search_util import SearchQueryHistory


def register_eddington_blueprint(
    repository: ActivityRepository, search_query_history: SearchQueryHistory
) -> Blueprint:
    blueprint = Blueprint("eddington", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = (
            apply_search_query(repository.meta, query)
            .dropna(subset=["start", "distance_km"])
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
            "eddington/index.html.j2",
            eddington_number=en_per_day,
            logarithmic_plot=_make_eddington_plot(
                eddington_df_per_day, en_per_day, "Days"
            ),
            eddington_per_week=en_per_week,
            eddington_per_week_plot=_make_eddington_plot(
                eddington_df_per_week, en_per_week, "Weeks"
            ),
            eddington_table=eddington_df_per_day.loc[
                (eddington_df_per_day["distance_km"] > en_per_day)
                & (eddington_df_per_day["distance_km"] <= en_per_day + 10)
            ].to_dict(orient="records"),
            eddington_table_weeks=eddington_df_per_week.loc[
                (eddington_df_per_week["distance_km"] > en_per_week)
                & (eddington_df_per_week["distance_km"] <= en_per_week + 10)
            ].to_dict(orient="records"),
            query=query.to_jinja(),
            yearly_eddington=_get_yearly_eddington(activities),
            eddington_number_history_plot=_get_eddington_number_history(activities),
        )

    return blueprint


def _get_distances_per_group(grouped) -> tuple[int, pd.DataFrame]:
    sum_per_group = grouped.apply(
        lambda group: int(sum(group["distance_km"])), include_groups=False
    )
    counts = dict(zip(*np.unique(sorted(sum_per_group), return_counts=True)))
    eddington = pd.DataFrame(
        {"distance_km": d, "count": counts.get(d, 0)}
        for d in range(max(counts.keys()) + 1)
    )
    eddington["total"] = eddington["count"][::-1].cumsum()[::-1]
    en = eddington.loc[eddington["total"] >= eddington["distance_km"]][
        "distance_km"
    ].iloc[-1]
    eddington["missing"] = eddington["distance_km"] - eddington["total"]
    return en, eddington


def _make_eddington_plot(eddington_df: pd.DataFrame, en: int, interval: str) -> dict:
    x = list(range(1, max(eddington_df["distance_km"]) + 1))
    return (
        (
            (
                alt.Chart(
                    eddington_df,
                    height=500,
                    width=800,
                    title=f"Eddington Number {en}",
                )
                .mark_area(interpolate="step")
                .encode(
                    alt.X(
                        "distance_km",
                        scale=alt.Scale(domainMin=0),
                        title="Distance / km",
                    ),
                    alt.Y(
                        "total",
                        scale=alt.Scale(domainMax=en + 10),
                        title=f"{interval} exceeding distance",
                    ),
                    [
                        alt.Tooltip("distance_km", title="Distance / km"),
                        alt.Tooltip("total", title=f"{interval} exceeding distance"),
                        alt.Tooltip("missing", title=f"{interval} missing for next"),
                    ],
                )
            )
            + (
                alt.Chart(pd.DataFrame({"distance_km": x, "total": x}))
                .mark_line(color="red")
                .encode(alt.X("distance_km"), alt.Y("total"))
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
    meta = meta.dropna(subset=["start", "distance_km"]).copy()
    meta["year"] = [start.year for start in meta["start"]]
    meta["date"] = [start.date() for start in meta["start"]]

    yearly_eddington = meta.groupby("year").apply(
        lambda group: _get_eddington_number(
            group.groupby("date").apply(
                lambda group2: int(group2["distance_km"].sum()), include_groups=False
            )
        ),
        include_groups=False,
    )
    return yearly_eddington.to_dict()


def _get_eddington_number_history(meta: pd.DataFrame) -> dict:

    daily_distances = meta.groupby("date").apply(
        lambda group2: int(group2["distance_km"].sum()), include_groups=False
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
            [
                alt.Tooltip("date", title="Date"),
                alt.Tooltip("eddington_number", title="Eddington number"),
            ],
        )
    ).to_json(format="vega")
