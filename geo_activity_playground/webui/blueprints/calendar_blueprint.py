import calendar
import collections
import datetime

import altair as alt
import pandas as pd
import sqlalchemy
from flask import Blueprint, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.datamodel import DB, Activity, TileVisit
from ...explorer.tile_visits import TileVisitAccessor


def _meta_with_local_start(repository: ActivityRepository) -> pd.DataFrame:
    meta = repository.meta
    if len(meta) == 0:
        return pd.DataFrame(
            columns=[
                "start_local",
                "year",
                "month",
                "day",
                "id",
                "distance_km",
                "elevation_gain",
                "hours_moving",
                "kind",
                "equipment",
            ]
        )
    return meta.loc[~pd.isna(meta["start_local"])].copy()


def _tile_first_visits(zoom: int) -> pd.DataFrame:
    rows = DB.session.execute(
        sqlalchemy.select(TileVisit.first_time).where(TileVisit.zoom == zoom)
    ).all()
    frame = pd.DataFrame(rows, columns=["first_time"])
    if len(frame) == 0:
        frame["year"] = pd.Series(dtype="int64")
        frame["month"] = pd.Series(dtype="int64")
        frame["day"] = pd.Series(dtype="int64")
        return frame
    frame["first_time"] = pd.to_datetime(frame["first_time"])
    frame = frame.loc[~pd.isna(frame["first_time"])].copy()
    frame["year"] = frame["first_time"].dt.year
    frame["month"] = frame["first_time"].dt.month
    frame["day"] = frame["first_time"].dt.day
    return frame


def _square_evolution_frame(
    tile_visit_accessor: TileVisitAccessor, zoom: int
) -> pd.DataFrame:
    frame = tile_visit_accessor.tile_state["evolution_state"][
        zoom
    ].square_evolution.copy()
    if len(frame) == 0:
        frame["year"] = pd.Series(dtype="int64")
        frame["month"] = pd.Series(dtype="int64")
        frame["day"] = pd.Series(dtype="int64")
        return frame
    frame["time"] = pd.to_datetime(frame["time"])
    frame = frame.loc[~pd.isna(frame["time"])].copy()
    frame["year"] = frame["time"].dt.year
    frame["month"] = frame["time"].dt.month
    frame["day"] = frame["time"].dt.day
    return frame


def _plot_monthly_progress(monthly: pd.DataFrame) -> str:
    if len(monthly) == 0:
        return ""
    base = alt.Chart(monthly, title=_("Monthly Distance and New Tiles"))
    distance = base.mark_bar().encode(
        alt.X("month:O", title=_("Month")),
        alt.Y("distance_km:Q", title=_("Distance / km")),
        alt.ColorValue("#0d6efd"),
        [
            alt.Tooltip("month:O", title=_("Month")),
            alt.Tooltip("distance_km:Q", title=_("Distance / km"), format=".1f"),
            alt.Tooltip("activities:Q", title=_("Activities")),
            alt.Tooltip("new_tiles:Q", title=_("New tiles")),
            alt.Tooltip("max_square_size:Q", title=_("Square size")),
        ],
    )
    new_tiles = base.mark_line(point=True, color="#ffc107").encode(
        alt.X("month:O", title=_("Month")),
        alt.Y("new_tiles:Q", title=_("New tiles")),
    )
    return (
        alt.layer(distance, new_tiles)
        .resolve_scale(y="independent")
        .to_json(format="vega")
    )


def _plot_category_distance(frame: pd.DataFrame, column: str, title: str) -> str:
    if len(frame) == 0:
        return ""
    grouped = (
        frame.groupby(column, dropna=False)["distance_km"].sum().reset_index().copy()
    )
    grouped[column] = grouped[column].fillna(_("Unknown"))
    grouped = grouped.sort_values("distance_km", ascending=False)
    return (
        alt.Chart(grouped, title=title)
        .mark_bar()
        .encode(
            alt.X("distance_km:Q", title=_("Distance / km")),
            alt.Y(f"{column}:N", sort="-x", title=_("Category")),
            [
                alt.Tooltip(f"{column}:N", title=_("Category")),
                alt.Tooltip("distance_km:Q", title=_("Distance / km"), format=".1f"),
            ],
        )
        .to_json(format="vega")
    )


def _plot_daily_progress(daily: pd.DataFrame) -> str:
    if len(daily) == 0:
        return ""
    base = alt.Chart(daily, title=_("Daily Distance and New Tiles"))
    distance = base.mark_bar().encode(
        alt.X("day:O", title=_("Day")),
        alt.Y("distance_km:Q", title=_("Distance / km")),
        alt.ColorValue("#198754"),
        [
            alt.Tooltip("day:O", title=_("Day")),
            alt.Tooltip("distance_km:Q", title=_("Distance / km"), format=".1f"),
            alt.Tooltip("activities:Q", title=_("Activities")),
            alt.Tooltip("new_tiles:Q", title=_("New tiles")),
            alt.Tooltip("max_square_size:Q", title=_("Square size")),
        ],
    )
    new_tiles = base.mark_line(point=True, color="#dc3545").encode(
        alt.X("day:O", title=_("Day")),
        alt.Y("new_tiles:Q", title=_("New tiles")),
    )
    return (
        alt.layer(distance, new_tiles)
        .resolve_scale(y="independent")
        .to_json(format="vega")
    )


def make_calendar_blueprint(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> Blueprint:
    blueprint = Blueprint("calendar", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        data = DB.session.execute(
            sqlalchemy.select(Activity.start, Activity.distance_km)
        ).all()
        df = pd.DataFrame(data)
        df["year"] = df["start"].dt.year
        df["month"] = df["start"].dt.month

        monthly_distance = df.groupby(
            ["year", "month"],
        ).apply(lambda group: sum(group["distance_km"]), include_groups=False)
        monthly_distance.name = "total_distance_km"
        monthly_pivot = (
            monthly_distance.reset_index()
            .pivot(index="month", columns="year", values="total_distance_km")
            .fillna(0.0)
        )

        yearly_distance = df.groupby(["year"]).apply(
            lambda group: sum(group["distance_km"]), include_groups=False
        )
        yearly_distance.name = "total_distance_km"
        yearly_distances = {
            row["year"]: row["total_distance_km"]
            for index, row in yearly_distance.reset_index().iterrows()
        }

        context = {
            "monthly_distances": monthly_pivot,
            "yearly_distances": yearly_distances,
        }
        return render_template("calendar/index.html.j2", **context)

    @blueprint.route("/<int:year>/<int:month>")
    def month(year: int, month: int) -> ResponseReturnValue:
        meta = repository.meta

        filtered = meta.loc[
            (meta["year"] == year) & (meta["month"] == month)
        ].sort_values("start_local")

        weeks = collections.defaultdict(dict)
        day_of_month = collections.defaultdict(dict)
        date = datetime.datetime(year, month, 1)
        while date.month == month:
            iso = date.isocalendar()
            weeks[iso.week][iso.weekday] = []
            day_of_month[iso.week][iso.weekday] = date.day
            date += datetime.timedelta(days=1)

        for _index, row in filtered.iterrows():
            iso = row["start_local"].isocalendar()
            weeks[iso.week][iso.weekday].append(
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "distance_km": row["distance_km"],
                    "id": row["id"],
                }
            )

        context = {
            "year": year,
            "month": month,
            "weeks": weeks,
            "day_of_month": day_of_month,
        }

        return render_template("calendar/month.html.j2", **context)

    @blueprint.route("/wrap")
    def wrap_latest() -> ResponseReturnValue:
        meta = _meta_with_local_start(repository)
        if len(meta) == 0:
            return render_template(
                "calendar/wrap-year.html.j2",
                year=None,
                years=[],
                metrics={},
                monthly_table=[],
                monthly_plot="",
                kind_plot="",
                equipment_plot="",
                year_rank=None,
                previous_year=None,
                next_year=None,
            )
        latest_year = int(meta["year"].max())
        return redirect(url_for(".wrap_year", year=latest_year))

    @blueprint.route("/wrap/<int:year>")
    def wrap_year(year: int) -> ResponseReturnValue:
        meta = _meta_with_local_start(repository)
        years = sorted({int(y) for y in meta["year"].dropna().unique()})
        if year not in years:
            if len(years) == 0:
                return render_template(
                    "calendar/wrap-year.html.j2",
                    year=year,
                    years=[],
                    metrics={},
                    monthly_table=[],
                    monthly_plot="",
                    kind_plot="",
                    equipment_plot="",
                    year_rank=None,
                    previous_year=None,
                    next_year=None,
                )
            return redirect(url_for(".wrap_year", year=years[-1]))

        period = meta.loc[meta["year"] == year].copy()
        tile_visits = _tile_first_visits(17)
        tile_year = tile_visits.loc[tile_visits["year"] == year].copy()
        square = _square_evolution_frame(tile_visit_accessor, 17)
        square_year = square.loc[square["year"] == year].copy()

        monthly_activity = (
            period.groupby("month", dropna=False)
            .agg(
                activities=("id", "count"),
                distance_km=("distance_km", "sum"),
                elevation_gain=("elevation_gain", "sum"),
                moving_hours=("hours_moving", "sum"),
            )
            .reset_index()
        )
        monthly_tiles = (
            tile_year.groupby("month").size().rename("new_tiles").reset_index()
            if len(tile_year)
            else pd.DataFrame({"month": [], "new_tiles": []})
        )
        monthly_square = (
            square_year.groupby("month")["max_square_size"]
            .max()
            .rename("max_square_size")
            .reset_index()
            if len(square_year)
            else pd.DataFrame({"month": [], "max_square_size": []})
        )
        monthly = pd.DataFrame({"month": list(range(1, 13))})
        monthly = monthly.merge(monthly_activity, on="month", how="left")
        monthly = monthly.merge(monthly_tiles, on="month", how="left")
        monthly = monthly.merge(monthly_square, on="month", how="left")
        monthly = monthly.fillna(0)

        yearly_distance = (
            meta.groupby("year")["distance_km"].sum().sort_values(ascending=False)
        )
        year_rank = int(yearly_distance.index.get_loc(year) + 1)

        previous_year = max((value for value in years if value < year), default=None)
        next_year = min((value for value in years if value > year), default=None)

        metrics = {
            "activities": int(len(period)),
            "distance_km": float(period["distance_km"].sum()),
            "elevation_gain": float(period["elevation_gain"].sum()),
            "moving_hours": float(period["hours_moving"].sum()),
            "new_tiles": int(len(tile_year)),
            "max_square_size": int(monthly["max_square_size"].max()),
        }

        monthly_table = monthly.to_dict("records")
        return render_template(
            "calendar/wrap-year.html.j2",
            year=year,
            years=years,
            metrics=metrics,
            monthly_table=monthly_table,
            monthly_plot=_plot_monthly_progress(monthly),
            kind_plot=_plot_category_distance(period, "kind", _("Distance by Kind")),
            equipment_plot=_plot_category_distance(
                period, "equipment", _("Distance by Equipment")
            ),
            year_rank=year_rank,
            previous_year=previous_year,
            next_year=next_year,
        )

    @blueprint.route("/wrap/<int:year>/<int:month>")
    def wrap_month(year: int, month: int) -> ResponseReturnValue:
        meta = _meta_with_local_start(repository)
        months = sorted(
            {
                (int(row["year"]), int(row["month"]))
                for _, row in meta[["year", "month"]].dropna().iterrows()
            }
        )
        period = meta.loc[(meta["year"] == year) & (meta["month"] == month)].copy()
        if len(period) == 0:
            return render_template(
                "calendar/wrap-month.html.j2",
                year=year,
                month=month,
                months=months,
                metrics={},
                daily_table=[],
                daily_plot="",
                kind_plot="",
                equipment_plot="",
                previous_month=None,
                next_month=None,
            )

        tile_visits = _tile_first_visits(17)
        tile_month = tile_visits.loc[
            (tile_visits["year"] == year) & (tile_visits["month"] == month)
        ].copy()
        square = _square_evolution_frame(tile_visit_accessor, 17)
        square_month = square.loc[
            (square["year"] == year) & (square["month"] == month)
        ].copy()

        _, max_day = calendar.monthrange(year, month)
        daily_activity = (
            period.groupby("day", dropna=False)
            .agg(
                activities=("id", "count"),
                distance_km=("distance_km", "sum"),
                elevation_gain=("elevation_gain", "sum"),
                moving_hours=("hours_moving", "sum"),
            )
            .reset_index()
        )
        daily_tiles = (
            tile_month.groupby("day").size().rename("new_tiles").reset_index()
            if len(tile_month)
            else pd.DataFrame({"day": [], "new_tiles": []})
        )
        daily_square = (
            square_month.groupby("day")["max_square_size"]
            .max()
            .rename("max_square_size")
            .reset_index()
            if len(square_month)
            else pd.DataFrame({"day": [], "max_square_size": []})
        )
        daily = pd.DataFrame({"day": list(range(1, max_day + 1))})
        daily = daily.merge(daily_activity, on="day", how="left")
        daily = daily.merge(daily_tiles, on="day", how="left")
        daily = daily.merge(daily_square, on="day", how="left")
        daily = daily.fillna(0)

        month_index = months.index((year, month))
        previous_month = months[month_index - 1] if month_index > 0 else None
        next_month = months[month_index + 1] if month_index + 1 < len(months) else None

        metrics = {
            "activities": int(len(period)),
            "distance_km": float(period["distance_km"].sum()),
            "elevation_gain": float(period["elevation_gain"].sum()),
            "moving_hours": float(period["hours_moving"].sum()),
            "new_tiles": int(len(tile_month)),
            "max_square_size": int(daily["max_square_size"].max()),
        }

        return render_template(
            "calendar/wrap-month.html.j2",
            year=year,
            month=month,
            months=months,
            metrics=metrics,
            daily_table=daily.to_dict("records"),
            daily_plot=_plot_daily_progress(daily),
            kind_plot=_plot_category_distance(period, "kind", _("Distance by Kind")),
            equipment_plot=_plot_category_distance(
                period, "equipment", _("Distance by Equipment")
            ),
            previous_month=previous_month,
            next_month=next_month,
        )

    return blueprint
