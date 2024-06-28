import datetime
import functools

import altair as alt
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository


class SummaryController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self) -> dict:
        df = embellished_activities(self._repository.meta)

        year_kind_total = (
            df[["year", "kind", "distance_km", "hours"]]
            .groupby(["year", "kind"])
            .sum()
            .reset_index()
        )

        return {
            "plot_distance_heatmap": plot_distance_heatmap(df),
            "plot_monthly_distance": plot_monthly_distance(df),
            "plot_yearly_distance": plot_yearly_distance(year_kind_total),
            "plot_year_cumulative": plot_year_cumulative(df),
            "tabulate_year_kind_mean": tabulate_year_kind_mean(df)
            .reset_index()
            .to_dict(orient="split"),
            "plot_weekly_distance": plot_weekly_distance(df),
        }


def embellished_activities(meta: pd.DataFrame) -> pd.DataFrame:
    df = meta.copy()
    df["year"] = [start.year for start in df["start"]]
    df["month"] = [start.month for start in df["start"]]
    df["day"] = [start.day for start in df["start"]]
    df["week"] = [start.isocalendar().week for start in df["start"]]
    df["hours"] = [
        elapsed_time.total_seconds() / 3600 for elapsed_time in df["elapsed_time"]
    ]
    del df["elapsed_time"]
    return df


def plot_distance_heatmap(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(
            meta.loc[
                (
                    meta["start"]
                    >= pd.to_datetime(
                        datetime.datetime.now(datetime.UTC)
                        - datetime.timedelta(days=2 * 365)
                    )
                )
            ],
            title="Daily Distance Heatmap",
        )
        .mark_rect()
        .encode(
            alt.X("date(start):O", title="Day of month"),
            alt.Y(
                "yearmonth(start):O",
                scale=alt.Scale(reverse=True),
                title="Year and month",
            ),
            alt.Color("sum(distance_km)", scale=alt.Scale(scheme="viridis")),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip(
                    "sum(distance_km)", format=".1f", title="Total distance / km"
                ),
                alt.Tooltip("count(distance_km)", title="Number of activities"),
            ],
        )
        .to_json(format="vega")
    )


def plot_monthly_distance(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(
            meta.loc[
                (
                    meta["start"]
                    >= pd.to_datetime(
                        datetime.datetime.now(datetime.UTC)
                        - datetime.timedelta(days=2 * 365)
                    )
                )
            ],
            title="Monthly Distance",
        )
        .mark_bar()
        .encode(
            alt.X("month(start)", title="Month"),
            alt.Y("sum(distance_km)", title="Distance / km"),
            alt.Color("kind", scale=alt.Scale(scheme="category10"), title="Kind"),
            alt.Column("year(start):O", title="Year"),
        )
        .resolve_axis(x="independent")
        .to_json(format="vega")
    )


def plot_yearly_distance(year_kind_total: pd.DataFrame) -> str:
    return (
        alt.Chart(year_kind_total, title="Total Distance per Year")
        .mark_bar()
        .encode(
            alt.X("year:O", title="Year"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("kind", title="Kind"),
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
        df[["year", "week", "distance_km"]]
        .groupby("year")
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
            alt.Color("year:N", title="Year"),
            [
                alt.Tooltip("week", title="Week"),
                alt.Tooltip("year:N", title="Year"),
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


def plot_weekly_distance(df: pd.DataFrame) -> str:
    week_kind_total_distance = (
        df[["year", "week", "kind", "distance_km"]]
        .groupby(["year", "week", "kind"])
        .sum()
        .reset_index()
    )
    week_kind_total_distance["year_week"] = [
        f"{year}-{week:02d}"
        for year, week in zip(
            week_kind_total_distance["year"], week_kind_total_distance["week"]
        )
    ]

    last_year = week_kind_total_distance["year"].iloc[-1]
    last_week = week_kind_total_distance["week"].iloc[-1]

    return (
        alt.Chart(
            week_kind_total_distance.loc[
                (week_kind_total_distance["year"] == last_year)
                | (week_kind_total_distance["year"] == last_year - 1)
                & (week_kind_total_distance["week"] >= last_week)
            ],
            title="Weekly Distance",
        )
        .mark_bar()
        .encode(
            alt.X("year_week", title="Year and Week"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("kind", title="Kind"),
            [
                alt.Tooltip("year_week", title="Year and Week"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip("distance_km", title="Distance / km"),
            ],
        )
        .to_json(format="vega")
    )
