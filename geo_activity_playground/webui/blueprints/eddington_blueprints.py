import datetime
from math import ceil

import altair as alt
import numpy as np
import pandas as pd
from flask import Blueprint
from flask import render_template
from flask import Request
from flask import request
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.meta_search import apply_search_filter
from ...core.meta_search import get_stored_queries
from ...core.meta_search import parse_search_params
from ...core.meta_search import primitives_to_jinja
from ...core.meta_search import register_search_query
from ..authenticator import Authenticator
from ..columns import column_distance
from ..columns import column_elevation_gain
from ..columns import ColumnDescription


def register_eddington_blueprint(
    repository: ActivityRepository,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("eddington", __name__, template_folder="templates")

    @blueprint.route("/")
    def distance() -> ResponseReturnValue:
        return _render_eddington_template(
            repository,
            request,
            authenticator,
            "distance",
            column_distance,
            [1],
        )

    @blueprint.route("/elevation_gain")
    def elevation_gain() -> ResponseReturnValue:
        return _render_eddington_template(
            repository,
            request,
            authenticator,
            "elevation_gain",
            column_elevation_gain,
            [20, 10, 1],
        )

    return blueprint


def _render_eddington_template(
    repository: ActivityRepository,
    request: Request,
    authenticator: Authenticator,
    template_name,
    column: ColumnDescription,
    divisor_values_avail: list[int],
) -> str:

    column_name = column.name
    display_name = column.display_name
    divisor = int(request.args.get("eddington_divisor") or divisor_values_avail[0])

    primitives = parse_search_params(request.args)

    if authenticator.is_authenticated():
        register_search_query(primitives)

    activities = (
        apply_search_filter(primitives).dropna(subset=["start_local", column_name]).copy()
    )

    assert (
        len(activities) > 0
    ), "The filter has selected zero elements, that cannot work here."

    en_per_day, eddington_df_per_day = _get_values_per_group(
        activities.groupby("date"), column_name, divisor
    )
    en_per_week, eddington_df_per_week = _get_values_per_group(
        activities.groupby(["iso_year", "week"]), column_name, divisor
    )

    stored_queries = get_stored_queries()
    search_query_favorites = [
        (str(q), q.to_url_str()) for q in stored_queries if q.is_favorite
    ]
    search_query_last = [
        (str(q), q.to_url_str()) for q in stored_queries if not q.is_favorite
    ]

    return render_template(
        f"eddington/{template_name}.html.j2",
        eddington_number=en_per_day,
        logarithmic_plot=_make_eddington_plot(
            eddington_df_per_day, en_per_day, "Days", column_name, display_name, divisor
        ),
        eddington_per_week=en_per_week,
        eddington_per_week_plot=_make_eddington_plot(
            eddington_df_per_week,
            en_per_week,
            "Weeks",
            column_name,
            display_name,
            divisor,
        ),
        eddington_table=eddington_df_per_day.loc[
            (eddington_df_per_day[column_name] > en_per_day)
            & (eddington_df_per_day[column_name] <= en_per_day + 10 * divisor)
            & (eddington_df_per_day[column_name] % divisor == 0)
        ].to_dict(orient="records"),
        eddington_table_weeks=eddington_df_per_week.loc[
            (eddington_df_per_week[column_name] > en_per_week)
            & (eddington_df_per_week[column_name] <= en_per_week + 10 * divisor)
            & (eddington_df_per_week[column_name] % divisor == 0)
        ].to_dict(orient="records"),
        query=primitives_to_jinja(primitives),
        search_query_favorites=search_query_favorites,
        search_query_last=search_query_last,
        yearly_eddington=_get_yearly_eddington(activities, column_name, divisor),
        eddington_number_history_plot=_get_eddington_number_history(
            activities, column_name, divisor
        ),
        eddington_divisor=divisor,
        divisor_values_avail=divisor_values_avail,
    )


def _get_values_per_group(grouped, column_name, divisor) -> tuple[int, pd.DataFrame]:
    sum_per_group = grouped.apply(
        lambda group: int(sum(group[column_name])), include_groups=False
    )
    counts = dict(zip(*np.unique(sorted(sum_per_group), return_counts=True)))
    eddington = pd.DataFrame(
        {column_name: d, "count": counts.get(d, 0)}
        for d in range(max(counts.keys()) + 1)
    )
    eddington["total"] = eddington["count"][::-1].cumsum()[::-1]
    eddington[f"{column_name}_div"] = eddington[column_name] // divisor
    en = (
        eddington.loc[eddington["total"] >= eddington[f"{column_name}_div"]][
            f"{column_name}_div"
        ].iloc[-1]
        * divisor
    )
    eddington["missing"] = eddington[f"{column_name}_div"] - eddington["total"]

    return en, eddington


def _make_eddington_plot(
    eddington_df: pd.DataFrame,
    en: int,
    interval: str,
    column_name: str,
    display_name: str,
    divisor: int,
) -> dict:
    x = list(range(1, max(eddington_df[column_name]) + 1))
    y = [v / divisor for v in x]
    return (
        (
            (
                alt.Chart(
                    eddington_df,
                    height=500,
                    width=800,
                    title=_("%(display_name)s Eddington Number %(en)s") % {"display_name": display_name, "en": en},
                )
                .mark_area(interpolate="step")
                .encode(
                    alt.X(
                        column_name,
                        scale=alt.Scale(domainMin=0, domainMax=en * 3),
                        title=display_name,
                    ),
                    alt.Y(
                        "total",
                        scale=alt.Scale(domainMax=en / divisor * 1.5),
                        title=_("%(interval)s exceeding %(display_name)s") % {"interval": interval, "display_name": display_name},
                    ),
                    [
                        alt.Tooltip(column_name, title=display_name),
                        alt.Tooltip(
                            "total", title=_("%(interval)s exceeding %(display_name)s") % {"interval": interval, "display_name": display_name}
                        ),
                        alt.Tooltip("missing", title=_("%(interval)s missing for next") % {"interval": interval}),
                    ],
                )
            )
            + (
                alt.Chart(pd.DataFrame({column_name: x, "total": y}))
                .mark_line(color="red")
                .encode(alt.X(column_name), alt.Y("total"))
            )
        )
        .interactive(bind_x=True, bind_y=True)
        .to_json(format="vega")
    )


def _get_eddington_number(elevation_gains: pd.Series, divisor: int) -> int:
    if len(elevation_gains) == 1:
        if elevation_gains.iloc[0] >= 1:
            return 1
        else:
            0

    sorted_elevation_gains = sorted(elevation_gains, reverse=True)

    for number_of_days, elevation_gain in enumerate(sorted_elevation_gains, 1):
        if elevation_gain / divisor < number_of_days:
            return (number_of_days - 1) * divisor


def _get_yearly_eddington(
    meta: pd.DataFrame, columnName: str, divisor: int
) -> dict[int, int]:
    meta = meta.dropna(subset=["start_local", columnName]).copy()

    yearly_eddington = meta.groupby("year").apply(
        lambda group: _get_eddington_number(
            group.groupby("date").apply(
                lambda group2: int(group2[columnName].sum()), include_groups=False
            ),
            divisor,
        ),
        include_groups=False,
    )
    return yearly_eddington.to_dict()


def _get_eddington_number_history(
    meta: pd.DataFrame, columnName: str, divisor: int
) -> dict:

    daily_elevation_gains = meta.groupby("date").apply(
        lambda group2: int(group2[columnName].sum()), include_groups=False
    )

    eddington_number_history = {"date": [], "eddington_number": []}
    top_days = []
    for date, elevation_gain in daily_elevation_gains.items():
        elevation_gain = elevation_gain / divisor
        if len(top_days) == 0:
            top_days.append(elevation_gain)
        else:
            if elevation_gain >= top_days[0]:
                top_days.append(elevation_gain)
                top_days.sort()
        while top_days[0] < len(top_days):
            top_days.pop(0)
        eddington_number_history["date"].append(
            datetime.datetime.combine(date, datetime.datetime.min.time())
        )
        eddington_number_history["eddington_number"].append(len(top_days) * divisor)
    history = pd.DataFrame(eddington_number_history)

    return (
        alt.Chart(history)
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("date", title=_("Date")),
            alt.Y("eddington_number", title=_("Eddington number")),
        )
    ).to_json(format="vega")
