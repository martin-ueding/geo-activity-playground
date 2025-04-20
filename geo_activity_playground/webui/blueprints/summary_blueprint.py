import collections
import datetime

import altair as alt
import pandas as pd
import sqlalchemy
from flask import Blueprint
from flask import render_template
from flask import request

from ...core.activities import ActivityRepository
from ...core.activities import make_geojson_from_time_series
from ...core.config import Config
from ...core.datamodel import DB
from ...core.datamodel import PlotSpec
from ...core.meta_search import apply_search_query
from ...core.parametric_plot import make_parametric_plot
from ..columns import column_distance
from ..columns import column_elevation_gain
from ..columns import ColumnDescription
from ..plot_util import make_kind_scale
from ..search_util import search_query_from_form
from ..search_util import SearchQueryHistory


def make_summary_blueprint(
    repository: ActivityRepository,
    config: Config,
    search_query_history: SearchQueryHistory,
) -> Blueprint:
    blueprint = Blueprint("summary", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = apply_search_query(repository.meta, query)

        kind_scale = make_kind_scale(repository.meta, config)
        df = activities

        nominations = nominate_activities(df)

        return render_template(
            "summary/index.html.j2",
            plot_distance_heatmaps=plot_heatmaps(df, column_distance, config),
            plot_elevation_gain_heatmaps=plot_heatmaps(
                df, column_elevation_gain, config
            ),
            plot_monthly_distance=plot_monthly_sums(df, column_distance, kind_scale),
            plot_monthly_elevation_gain=plot_monthly_sums(
                df, column_elevation_gain, kind_scale
            ),
            plot_yearly_distance=plot_yearly_sums(df, column_distance, kind_scale),
            plot_yearly_elevation_gain=plot_yearly_sums(
                df, column_elevation_gain, kind_scale
            ),
            plot_year_cumulative=plot_year_cumulative(df, column_distance),
            plot_year_elevation_gain_cumulative=plot_year_cumulative(
                df, column_elevation_gain
            ),
            tabulate_year_kind_mean=tabulate_year_kind_mean(df, column_distance)
            .reset_index()
            .to_dict(orient="split"),
            tabulate_year_kind_mean_elevation_gain=tabulate_year_kind_mean(
                df, column_elevation_gain
            )
            .reset_index()
            .to_dict(orient="split"),
            plot_weekly_distance=plot_weekly_sums(df, column_distance, kind_scale),
            plot_weekly_elevation_gain=plot_weekly_sums(
                df, column_elevation_gain, kind_scale
            ),
            nominations=[
                (
                    repository.get_activity_by_id(activity_id),
                    reasons,
                    make_geojson_from_time_series(
                        repository.get_time_series(activity_id)
                    ),
                )
                for activity_id, reasons in nominations.items()
            ],
            query=query.to_jinja(),
            custom_plots=[
                (spec, make_parametric_plot(repository.meta, spec))
                for spec in DB.session.scalars(sqlalchemy.select(PlotSpec)).all()
            ],
        )

    return blueprint


def nominate_activities(meta: pd.DataFrame) -> dict[int, list[str]]:
    nominations: dict[int, list[str]] = collections.defaultdict(list)

    _nominate_activities_inner(meta, "", nominations)

    for kind, group in meta.groupby("kind"):
        _nominate_activities_inner(group, f" for {kind}", nominations)
    for equipment, group in meta.groupby("equipment"):
        _nominate_activities_inner(group, f" with {equipment}", nominations)

    return nominations


def _nominate_activities_inner(
    meta: pd.DataFrame, title_suffix: str, nominations: dict[int, list[str]]
) -> None:
    ratings = [
        ("distance_km", "Greatest distance", "{:.1f} km"),
        ("elapsed_time", "Longest elapsed time", "{}"),
        ("average_speed_moving_kmh", "Highest average moving speed", "{:.1f} km/h"),
        ("average_speed_elapsed_kmh", "Highest average elapsed speed", "{:.1f} km/h"),
        ("calories", "Most calories burnt", "{:.0f}"),
        ("steps", "Most steps", "{:.0f}"),
        ("elevation_gain", "Largest elevation gain", "{:.0f} m"),
    ]

    for variable, title, format_str in ratings:
        if variable in meta.columns and not pd.isna(meta[variable]).all():
            i = meta[variable].idxmax()
            value = meta.loc[i, variable]
            format_applied = format_str.format(value)
            nominations[i].append(f"{title}{title_suffix}: {format_applied}")


def plot_heatmaps(
    meta: pd.DataFrame, column: ColumnDescription, config: Config
) -> dict[int, str]:
    return {
        year: alt.Chart(
            meta.loc[(meta["year"] == year)],
            title=f"Daily {column.display_name} Heatmap",
        )
        .mark_rect()
        .encode(
            alt.X("date(start):O", title="Day of month"),
            alt.Y(
                "yearmonth(start):O",
                # scale=alt.Scale(reverse=True),
                title="Year and month",
            ),
            alt.Color(
                f"sum({column.name})",
                scale=alt.Scale(scheme=config.color_scheme_for_counts),
            ),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip(
                    f"sum({column.name})",
                    format=column.format,
                    title=f"Total {column.display_name} / {column.unit}",
                ),
                alt.Tooltip(f"count({column.name})", title="Number of activities"),
            ],
        )
        .to_json(format="vega")
        for year in sorted(meta["year"].unique())
    }


def plot_monthly_sums(
    meta: pd.DataFrame, column: ColumnDescription, kind_scale: alt.Scale
) -> str:
    return (
        alt.Chart(
            meta.loc[
                (
                    meta["start"]
                    >= pd.to_datetime(
                        datetime.datetime.now() - datetime.timedelta(days=2 * 365)
                    )
                )
            ],
            title=f"Monthly {column.display_name}",
        )
        .mark_bar()
        .encode(
            alt.X("month(start)", title="Month"),
            alt.Y(
                f"sum({column.name})",
                title=f"{column.display_name} / {column.unit}",
            ),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            alt.Column("year(start):O", title="Year"),
            [
                alt.Tooltip("yearmonth(start)", title="Year and Month"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip(
                    f"sum({column.name})",
                    format=column.format,
                    title=f"Total {column.display_name} / {column.unit}",
                ),
                alt.Tooltip(f"count({column.name})", title="Number of activities"),
            ],
        )
        .resolve_axis(x="independent")
        .to_json(format="vega")
    )


def plot_yearly_sums(
    df: pd.DataFrame, column: ColumnDescription, kind_scale: alt.Scale
) -> str:
    year_kind_total = (
        df[["year", "kind", column.name, "hours"]]
        .groupby(["year", "kind"])
        .sum()
        .reset_index()
    )

    return (
        alt.Chart(year_kind_total, title=f"Total {column.display_name} per Year")
        .mark_bar()
        .encode(
            alt.X("year:O", title="Year"),
            alt.Y(column.name, title=f"{column.display_name} / {column.unit}"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip(
                    column.name,
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .to_json(format="vega")
    )


def plot_year_cumulative(df: pd.DataFrame, column: ColumnDescription) -> str:
    year_cumulative = (
        df[["iso_year", "week", column.name]]
        .groupby("iso_year")
        .apply(
            lambda group: pd.DataFrame(
                {
                    "week": group["week"],
                    column.name: group[column.name].cumsum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    return (
        alt.Chart(
            year_cumulative,
            width=500,
            title=f"Cumulative {column.display_name} per Year",
        )
        .mark_line()
        .encode(
            alt.X("week", title="Week"),
            alt.Y(column.name, title=f"{column.display_name} / {column.unit}"),
            alt.Color("iso_year:N", title="Year"),
            [
                alt.Tooltip("week", title="Week"),
                alt.Tooltip("iso_year:N", title="Year"),
                alt.Tooltip(
                    column.name,
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .interactive()
        .to_json(format="vega")
    )


def tabulate_year_kind_mean(
    df: pd.DataFrame, column: ColumnDescription
) -> pd.DataFrame:
    year_kind_mean = (
        df[["year", "kind", column.name, "hours"]]
        .groupby(["year", "kind"])
        .mean()
        .reset_index()
    )

    year_kind_mean_distance = year_kind_mean.pivot(
        index="year", columns="kind", values=column.name
    )

    return year_kind_mean_distance


def plot_weekly_sums(
    df: pd.DataFrame, column: ColumnDescription, kind_scale: alt.Scale
) -> str:
    week_kind_total_distance = (
        df[["iso_year", "week", "kind", column.name]]
        .groupby(["iso_year", "week", "kind"])
        .sum()
        .reset_index()
    )
    week_kind_total_distance["year_week"] = [
        f"{year}-{week:02d}"
        for year, week in zip(
            week_kind_total_distance["iso_year"], week_kind_total_distance["week"]
        )
    ]

    last_year = week_kind_total_distance["iso_year"].iloc[-1]
    last_week = week_kind_total_distance["week"].iloc[-1]

    return (
        alt.Chart(
            week_kind_total_distance.loc[
                (week_kind_total_distance["iso_year"] == last_year)
                | (week_kind_total_distance["iso_year"] == last_year - 1)
                & (week_kind_total_distance["week"] >= last_week)
            ],
            title=f"Weekly {column.display_name}",
        )
        .mark_bar()
        .encode(
            alt.X("year_week", title="Year and Week"),
            alt.Y(column.name, title=f"{column.display_name} / {column.unit}"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("year_week", title="Year and Week"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip(
                    column.name,
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .to_json(format="vega")
    )
