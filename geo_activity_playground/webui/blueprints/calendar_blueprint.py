import calendar
import collections
import datetime
import zoneinfo

import altair as alt
import pandas as pd
import sqlalchemy
from flask import Blueprint, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.config import Config
from ...core.datamodel import DB, Activity, TileVisit
from ...explorer.tile_visits import TileVisitAccessor, get_cluster_tile_activations_df


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


def _local_ymd_from_utc(
    event_time: datetime.datetime | pd.Timestamp | None,
    activity_start: datetime.datetime | pd.Timestamp | None,
    iana_timezone: str | None,
) -> tuple[int | None, int | None, int | None]:
    if event_time is None or pd.isna(event_time):
        if activity_start is None or pd.isna(activity_start):
            return None, None, None
        timestamp = pd.Timestamp(activity_start)
    else:
        timestamp = pd.Timestamp(event_time)
    if timestamp.tz is None:
        timestamp = timestamp.tz_localize(zoneinfo.ZoneInfo("UTC"))

    timezone_name = "UTC" if iana_timezone is None else iana_timezone
    try:
        timezone = zoneinfo.ZoneInfo(timezone_name)
    except zoneinfo.ZoneInfoNotFoundError:
        timezone = zoneinfo.ZoneInfo("UTC")
    local = timestamp.tz_convert(timezone)
    return int(local.year), int(local.month), int(local.day)


def _tile_first_visits(zoom: int) -> pd.DataFrame:
    rows = DB.session.execute(
        sqlalchemy.select(
            TileVisit.first_time,
            TileVisit.tile_x,
            TileVisit.tile_y,
            Activity.start.label("activity_start"),
            Activity.iana_timezone,
        )
        .where(TileVisit.zoom == zoom)
        .join(Activity, Activity.id == TileVisit.first_activity_id)
    ).all()
    frame = pd.DataFrame(
        rows,
        columns=["first_time", "tile_x", "tile_y", "activity_start", "iana_timezone"],
    )
    if len(frame) == 0:
        frame["year"] = pd.Series(dtype="int64")
        frame["month"] = pd.Series(dtype="int64")
        frame["day"] = pd.Series(dtype="int64")
        return frame
    frame["first_time"] = pd.to_datetime(frame["first_time"])
    frame["activity_start"] = pd.to_datetime(frame["activity_start"])
    local_dates = [
        _local_ymd_from_utc(
            event_time,
            activity_start,
            None if pd.isna(iana_timezone) else str(iana_timezone),
        )
        for event_time, activity_start, iana_timezone in zip(
            frame["first_time"],
            frame["activity_start"],
            frame["iana_timezone"],
        )
    ]
    frame["year"] = [year for year, _, _ in local_dates]
    frame["month"] = [month for _, month, _ in local_dates]
    frame["day"] = [day for _, _, day in local_dates]
    frame = frame.loc[
        ~pd.isna(frame["year"]) & ~pd.isna(frame["month"]) & ~pd.isna(frame["day"])
    ].copy()
    frame["year"] = frame["year"].astype("int64")
    frame["month"] = frame["month"].astype("int64")
    frame["day"] = frame["day"].astype("int64")
    return frame


def _cluster_tile_activations(zoom: int) -> pd.DataFrame:
    frame = get_cluster_tile_activations_df(zoom)
    if len(frame) == 0:
        frame["year"] = pd.Series(dtype="int64")
        frame["month"] = pd.Series(dtype="int64")
        frame["day"] = pd.Series(dtype="int64")
        return frame
    frame["time"] = pd.to_datetime(frame["time"])
    activity_ids = [
        int(activity_id)
        for activity_id in frame["activity_id"].dropna().unique()
        if pd.notna(activity_id)
    ]
    activity_rows = DB.session.execute(
        sqlalchemy.select(Activity.id, Activity.start, Activity.iana_timezone).where(
            Activity.id.in_(activity_ids)
        )
    ).all()
    activity_meta = {
        int(activity_id): (start, iana_timezone)
        for activity_id, start, iana_timezone in activity_rows
    }
    local_dates = []
    for event_time, activity_id in zip(frame["time"], frame["activity_id"]):
        if pd.isna(activity_id):
            start, iana_timezone = None, None
        else:
            start, iana_timezone = activity_meta.get(int(activity_id), (None, None))
        local_dates.append(
            _local_ymd_from_utc(
                event_time,
                start,
                None
                if iana_timezone is None or pd.isna(iana_timezone)
                else str(iana_timezone),
            )
        )
    frame["year"] = [year for year, _, _ in local_dates]
    frame["month"] = [month for _, month, _ in local_dates]
    frame["day"] = [day for _, _, day in local_dates]
    frame = frame.loc[
        ~pd.isna(frame["year"]) & ~pd.isna(frame["month"]) & ~pd.isna(frame["day"])
    ].copy()
    frame["year"] = frame["year"].astype("int64")
    frame["month"] = frame["month"].astype("int64")
    frame["day"] = frame["day"].astype("int64")
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
            alt.Tooltip("new_cluster_tiles:Q", title=_("New cluster tiles")),
            alt.Tooltip("max_square_size:Q", title=_("Square size")),
        ],
    )
    new_tiles = base.mark_line(point=True, color="#ffc107").encode(
        alt.X("month:O", title=_("Month")),
        alt.Y("new_tiles:Q", title=_("New tiles")),
    )
    new_cluster_tiles = base.mark_line(point=True, color="#6f42c1").encode(
        alt.X("month:O", title=_("Month")),
        alt.Y("new_cluster_tiles:Q", title=_("New cluster tiles")),
    )
    return (
        alt.layer(distance, new_tiles, new_cluster_tiles)
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
            alt.Tooltip("new_cluster_tiles:Q", title=_("New cluster tiles")),
            alt.Tooltip("max_square_size:Q", title=_("Square size")),
        ],
    )
    new_tiles = base.mark_line(point=True, color="#dc3545").encode(
        alt.X("day:O", title=_("Day")),
        alt.Y("new_tiles:Q", title=_("New tiles")),
    )
    new_cluster_tiles = base.mark_line(point=True, color="#6f42c1").encode(
        alt.X("day:O", title=_("Day")),
        alt.Y("new_cluster_tiles:Q", title=_("New cluster tiles")),
    )
    return (
        alt.layer(distance, new_tiles, new_cluster_tiles)
        .resolve_scale(y="independent")
        .to_json(format="vega")
    )


def _format_elapsed_time(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    total_seconds = int(pd.Timedelta(value).total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _outstanding_activities(period: pd.DataFrame) -> list[dict]:
    if len(period) == 0:
        return []

    categories = [
        ("distance_km", _("Longest distance"), lambda value: f"{float(value):.1f} km"),
        ("elapsed_time", _("Longest time"), _format_elapsed_time),
        ("num_new_tiles_17", _("Most new tiles"), lambda value: f"{int(value)}"),
    ]

    nominations: dict[int, dict] = {}
    for column, title, formatter in categories:
        if column not in period.columns or pd.isna(period[column]).all():
            continue
        row_index = period[column].idxmax()
        row = period.loc[row_index]
        activity_id = int(row["id"])
        nomination = nominations.setdefault(
            activity_id,
            {
                "id": activity_id,
                "name": str(row["name"]),
                "date": row["start_local"],
                "reasons": [],
            },
        )
        nomination["reasons"].append({"title": title, "value": formatter(row[column])})
    return list(nominations.values())


def _square_size_at(square_history: pd.DataFrame, checkpoints: pd.Series) -> pd.Series:
    if len(square_history) == 0:
        return pd.Series([0] * len(checkpoints), dtype="int64")

    history = square_history[["time", "max_square_size"]].sort_values("time").copy()
    probe = pd.DataFrame({"checkpoint": pd.to_datetime(checkpoints)}).sort_values(
        "checkpoint"
    )
    merged = pd.merge_asof(
        probe,
        history,
        left_on="checkpoint",
        right_on="time",
        direction="backward",
    )
    merged["max_square_size"] = merged["max_square_size"].fillna(0).astype("int64")
    return merged["max_square_size"].reset_index(drop=True)


def make_calendar_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
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
                outstanding_activities=[],
                primary_zoom=14,
                zoom_stats=[],
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
                    outstanding_activities=[],
                    primary_zoom=14,
                    zoom_stats=[],
                )
            return redirect(url_for(".wrap_year", year=years[-1]))

        period = meta.loc[meta["year"] == year].copy()
        selected_zooms = sorted(set(config.explorer_zoom_levels))
        primary_zoom = (
            14
            if 14 in selected_zooms
            else (selected_zooms[0] if selected_zooms else 14)
        )
        square = _square_evolution_frame(tile_visit_accessor, primary_zoom)

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

        zoom_stats = []
        tile_year_primary = pd.DataFrame(columns=["year", "month", "day"])
        cluster_year_primary = pd.DataFrame(columns=["year", "month", "day"])
        for zoom in selected_zooms:
            tile_visits = _tile_first_visits(zoom)
            cluster_activations = _cluster_tile_activations(zoom)
            tile_year = tile_visits.loc[tile_visits["year"] == year].copy()
            cluster_year = cluster_activations.loc[
                cluster_activations["year"] == year
            ].copy()
            square_zoom = _square_evolution_frame(tile_visit_accessor, zoom)
            year_end = pd.Series([pd.Timestamp(year=year, month=12, day=31)])
            square_size = int(_square_size_at(square_zoom, year_end).iloc[0])
            zoom_stats.append(
                {
                    "zoom": zoom,
                    "new_tiles": int(len(tile_year)),
                    "new_cluster_tiles": int(len(cluster_year)),
                    "max_square_size": square_size,
                }
            )
            if zoom == primary_zoom:
                tile_year_primary = tile_year
                cluster_year_primary = cluster_year

        monthly_tiles = (
            tile_year_primary.groupby("month").size().rename("new_tiles").reset_index()
            if len(tile_year_primary)
            else pd.DataFrame({"month": [], "new_tiles": []})
        )
        monthly_cluster_tiles = (
            cluster_year_primary.groupby("month")
            .size()
            .rename("new_cluster_tiles")
            .reset_index()
            if len(cluster_year_primary)
            else pd.DataFrame({"month": [], "new_cluster_tiles": []})
        )
        monthly = pd.DataFrame({"month": list(range(1, 13))})
        monthly = monthly.merge(monthly_activity, on="month", how="left")
        monthly = monthly.merge(monthly_tiles, on="month", how="left")
        monthly = monthly.merge(monthly_cluster_tiles, on="month", how="left")
        month_end = pd.to_datetime(
            {
                "year": [year] * len(monthly),
                "month": monthly["month"],
                "day": [1] * len(monthly),
            }
        ) + pd.offsets.MonthEnd(1)
        monthly["max_square_size"] = _square_size_at(square, month_end)
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
            "new_tiles": int(len(tile_year_primary)),
            "new_cluster_tiles": int(len(cluster_year_primary)),
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
            outstanding_activities=_outstanding_activities(period),
            primary_zoom=primary_zoom,
            zoom_stats=zoom_stats,
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
                outstanding_activities=[],
                primary_zoom=14,
                zoom_stats=[],
            )

        selected_zooms = sorted(set(config.explorer_zoom_levels))
        primary_zoom = (
            14
            if 14 in selected_zooms
            else (selected_zooms[0] if selected_zooms else 14)
        )
        square = _square_evolution_frame(tile_visit_accessor, primary_zoom)

        max_day = calendar.monthrange(year, month)[1]
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
        zoom_stats = []
        tile_month_primary = pd.DataFrame(columns=["year", "month", "day"])
        cluster_month_primary = pd.DataFrame(columns=["year", "month", "day"])
        for zoom in selected_zooms:
            tile_visits = _tile_first_visits(zoom)
            cluster_activations = _cluster_tile_activations(zoom)
            tile_month = tile_visits.loc[
                (tile_visits["year"] == year) & (tile_visits["month"] == month)
            ].copy()
            cluster_month = cluster_activations.loc[
                (cluster_activations["year"] == year)
                & (cluster_activations["month"] == month)
            ].copy()
            square_zoom = _square_evolution_frame(tile_visit_accessor, zoom)
            month_end = pd.Series([pd.Timestamp(year=year, month=month, day=max_day)])
            square_size = int(_square_size_at(square_zoom, month_end).iloc[0])
            zoom_stats.append(
                {
                    "zoom": zoom,
                    "new_tiles": int(len(tile_month)),
                    "new_cluster_tiles": int(len(cluster_month)),
                    "max_square_size": square_size,
                }
            )
            if zoom == primary_zoom:
                tile_month_primary = tile_month
                cluster_month_primary = cluster_month

        daily_tiles = (
            tile_month_primary.groupby("day").size().rename("new_tiles").reset_index()
            if len(tile_month_primary)
            else pd.DataFrame({"day": [], "new_tiles": []})
        )
        daily_cluster_tiles = (
            cluster_month_primary.groupby("day")
            .size()
            .rename("new_cluster_tiles")
            .reset_index()
            if len(cluster_month_primary)
            else pd.DataFrame({"day": [], "new_cluster_tiles": []})
        )
        daily = pd.DataFrame({"day": list(range(1, max_day + 1))})
        daily = daily.merge(daily_activity, on="day", how="left")
        daily = daily.merge(daily_tiles, on="day", how="left")
        daily = daily.merge(daily_cluster_tiles, on="day", how="left")
        day_end = pd.to_datetime(
            {
                "year": [year] * len(daily),
                "month": [month] * len(daily),
                "day": daily["day"],
            }
        )
        daily["max_square_size"] = _square_size_at(square, day_end)
        daily = daily.fillna(0)

        month_index = months.index((year, month))
        previous_month = months[month_index - 1] if month_index > 0 else None
        next_month = months[month_index + 1] if month_index + 1 < len(months) else None

        metrics = {
            "activities": int(len(period)),
            "distance_km": float(period["distance_km"].sum()),
            "elevation_gain": float(period["elevation_gain"].sum()),
            "moving_hours": float(period["hours_moving"].sum()),
            "new_tiles": int(len(tile_month_primary)),
            "new_cluster_tiles": int(len(cluster_month_primary)),
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
            outstanding_activities=_outstanding_activities(period),
            primary_zoom=primary_zoom,
            zoom_stats=zoom_stats,
        )

    return blueprint
