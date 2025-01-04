import collections
import datetime

import altair as alt
import pandas as pd
from flask import Blueprint
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import make_geojson_from_time_series
from geo_activity_playground.core.config import Config
from geo_activity_playground.webui.plot_util import make_kind_scale


def make_summary_blueprint(repository: ActivityRepository, config: Config) -> Blueprint:
    blueprint = Blueprint("summary", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        kind_scale = make_kind_scale(repository.meta, config)
        df = embellished_activities(repository.meta)
        # df = df.loc[df["consider_for_achievements"]]

        year_kind_total = (
            df[["year", "kind", "distance_km", "hours"]]
            .groupby(["year", "kind"])
            .sum()
            .reset_index()
        )

        return render_template(
            "summary/index.html.j2",
            plot_distance_heatmaps=plot_distance_heatmaps(df, config),
            plot_monthly_distance=plot_monthly_distance(df, kind_scale),
            plot_yearly_distance=plot_yearly_distance(year_kind_total, kind_scale),
            plot_year_cumulative=plot_year_cumulative(df),
            tabulate_year_kind_mean=tabulate_year_kind_mean(df)
            .reset_index()
            .to_dict(orient="split"),
            plot_weekly_distance=plot_weekly_distance(df, kind_scale),
            nominations=[
                (
                    repository.get_activity_by_id(activity_id),
                    reasons,
                    make_geojson_from_time_series(
                        repository.get_time_series(activity_id)
                    ),
                )
                for activity_id, reasons in nominate_activities(repository.meta).items()
            ],
        )

    return blueprint


def nominate_activities(meta: pd.DataFrame) -> dict[int, list[str]]:
    nominations: dict[int, list[str]] = collections.defaultdict(list)

    subset = meta.loc[meta["consider_for_achievements"]]

    i = subset["distance_km"].idxmax()
    nominations[i].append(f"Greatest distance: {meta.loc[i].distance_km:.1f} km")

    i = subset["elapsed_time"].idxmax()
    nominations[i].append(f"Longest elapsed time: {meta.loc[i].elapsed_time}")

    if "calories" in subset.columns and not pd.isna(subset["calories"]).all():
        i = subset["calories"].idxmax()
        nominations[i].append(f"Most calories burnt: {meta.loc[i].calories:.0f} kcal")

    if "steps" in subset.columns and not pd.isna(subset["steps"]).all():
        i = subset["steps"].idxmax()
        nominations[i].append(f"Most steps: {meta.loc[i].steps:.0f}")

    for kind, group in meta.groupby("kind"):
        for key, text in [
            (
                "distance_km",
                lambda row: f"Greatest distance for {row.kind}: {row.distance_km:.1f} km",
            ),
            (
                "elapsed_time",
                lambda row: f"Longest elapsed time for {row.kind}: {row.elapsed_time}",
            ),
            (
                "calories",
                lambda row: f"Most calories burnt for {row.kind}: {row.calories:.0f} kcal",
            ),
            ("steps", lambda row: f"Most steps for {row.kind}: {row.steps:.0f}"),
        ]:
            if key in group.columns:
                series = group[key]
                if not pd.isna(series).all():
                    i = series.idxmax()
                    if not pd.isna(i):
                        nominations[i].append(text(meta.loc[i]))

    return nominations


def embellished_activities(meta: pd.DataFrame) -> pd.DataFrame:
    df = meta.loc[~pd.isna(meta["start"])].copy()
    df["year"] = [start.year for start in df["start"]]
    df["month"] = [start.month for start in df["start"]]
    df["day"] = [start.day for start in df["start"]]
    df["week"] = [start.isocalendar().week for start in df["start"]]
    df["iso_year"] = [start.isocalendar().year for start in df["start"]]
    df["hours"] = [
        elapsed_time.total_seconds() / 3600 for elapsed_time in df["elapsed_time"]
    ]
    del df["elapsed_time"]
    return df


def plot_distance_heatmaps(meta: pd.DataFrame, config: Config) -> dict[int, str]:
    return {
        year: alt.Chart(
            meta.loc[(meta["year"] == year)],
            title="Daily Distance Heatmap",
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
                "sum(distance_km)",
                scale=alt.Scale(scheme=config.color_scheme_for_counts),
            ),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip(
                    "sum(distance_km)", format=".1f", title="Total distance / km"
                ),
                alt.Tooltip("count(distance_km)", title="Number of activities"),
            ],
        )
        .to_json(format="vega")
        for year in sorted(meta["year"].unique())
    }


def plot_monthly_distance(meta: pd.DataFrame, kind_scale: alt.Scale) -> str:
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
            title="Monthly Distance",
        )
        .mark_bar()
        .encode(
            alt.X("month(start)", title="Month"),
            alt.Y("sum(distance_km)", title="Distance / km"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            alt.Column("year(start):O", title="Year"),
        )
        .resolve_axis(x="independent")
        .to_json(format="vega")
    )


def plot_yearly_distance(year_kind_total: pd.DataFrame, kind_scale: alt.Scale) -> str:
    return (
        alt.Chart(year_kind_total, title="Total Distance per Year")
        .mark_bar()
        .encode(
            alt.X("year:O", title="Year"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip("distance_km", title="Distance / km"),
            ],
        )
        .to_json(format="vega")
    )


def plot_year_cumulative(df: pd.DataFrame) -> str:
    year_cumulative = (
        df[["iso_year", "week", "distance_km"]]
        .groupby("iso_year")
        .apply(
            lambda group: pd.DataFrame(
                {"week": group["week"], "distance_km": group["distance_km"].cumsum()}
            ),
            include_groups=False,
        )
        .reset_index()
    )

    return (
        alt.Chart(year_cumulative, width=500, title="Cumultative Distance per Year")
        .mark_line()
        .encode(
            alt.X("week", title="Week"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("iso_year:N", title="Year"),
            [
                alt.Tooltip("week", title="Week"),
                alt.Tooltip("iso_year:N", title="Year"),
                alt.Tooltip("distance_km", title="Distance / km"),
            ],
        )
        .interactive()
        .to_json(format="vega")
    )


def tabulate_year_kind_mean(df: pd.DataFrame) -> pd.DataFrame:
    year_kind_mean = (
        df[["year", "kind", "distance_km", "hours"]]
        .groupby(["year", "kind"])
        .mean()
        .reset_index()
    )

    year_kind_mean_distance = year_kind_mean.pivot(
        index="year", columns="kind", values="distance_km"
    )

    return year_kind_mean_distance


def plot_weekly_distance(df: pd.DataFrame, kind_scale: alt.Scale) -> str:
    week_kind_total_distance = (
        df[["iso_year", "week", "kind", "distance_km"]]
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
            title="Weekly Distance",
        )
        .mark_bar()
        .encode(
            alt.X("year_week", title="Year and Week"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("year_week", title="Year and Week"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip("distance_km", title="Distance / km"),
            ],
        )
        .to_json(format="vega")
    )
