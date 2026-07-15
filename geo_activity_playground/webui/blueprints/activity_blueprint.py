import datetime
import io
import logging
import pathlib
import re
import zoneinfo

import altair as alt
import geojson
import matplotlib
import numpy as np
import pandas as pd
import sqlalchemy
from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from PIL import Image, ImageDraw, ImageFont

from ...core.activities import (
    ActivityRepository,
    make_geojson_from_time_series,
    make_geojson_line_segments_with_columns,
    make_geojson_progress_markers_from_time_series,
    make_geojson_progress_markers_time_based,
)
from ...core.config import ConfigAccessor
from ...core.datamodel import (
    DB,
    DEFAULT_UNKNOWN_NAME,
    Activity,
    Equipment,
    Kind,
    MapConfig,
    PrivacyZone,
    Tag,
    TileVisit,
    get_or_make_equipment,
    get_or_make_kind,
)
from ...core.enrichment import update_and_commit
from ...core.heart_rate import HeartRateZoneComputer
from ...core.raster_map import (
    OSM_MAX_ZOOM,
    OSM_TILE_SIZE,
    map_image_from_tile_bounds,
    tile_bounds_around_center,
)
from ...explorer.grid_file import make_grid_file_geojson, make_grid_points
from ...explorer.tile_visits import (
    refresh_tile_visits_for_activity,
    remove_activity_from_tile_state,
)
from ..authenticator import Authenticator, needs_authentication
from ..columns import TIME_SERIES_COLUMNS

logger = logging.getLogger(__name__)


def make_activity_blueprint(
    repository: ActivityRepository,
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
    heart_rate_zone_computer: HeartRateZoneComputer,
) -> Blueprint:
    blueprint = Blueprint("activity", __name__, template_folder="templates")

    @blueprint.route("/all")
    def all() -> ResponseReturnValue:
        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in repository.get_time_series(
                                activity.id
                            ).groupby("segment_id")
                        ]
                    ),
                    properties={
                        "color": matplotlib.colors.to_hex(cmap(i % 8)),
                        "activity_name": activity.name,
                        "activity_id": str(activity.id),
                    },
                )
                for i, activity in enumerate(repository.iter_activities())
            ]
        )

        context = {
            "geojson": geojson.dumps(fc),
        }
        return render_template("activity/lines.html.j2", **context)

    @blueprint.route("/<int:id>")
    def show(id: str) -> ResponseReturnValue:
        config = config_accessor.ui()
        activity = repository.get_activity_by_id(id)

        time_series = repository.get_time_series(id)
        line_json = make_geojson_from_time_series(
            time_series, config.eighth_marker_min_distance_km
        )

        meta = repository.meta
        similar_activities = meta.loc[
            (meta.name == activity.name) & (meta.id != activity.id)
        ]
        similar_activities = [row for _, row in similar_activities.iterrows()]
        similar_activities.reverse()

        # Query new tiles discovered by this activity from the database
        new_tiles_geojson = {}
        new_tiles_per_zoom = {}
        cluster_diff_geojson_urls = {}
        for zoom in sorted(config.explorer_zoom_levels):
            first_visits = (
                DB.session.query(TileVisit)
                .filter(
                    TileVisit.first_activity_id == activity.id,
                    TileVisit.zoom == zoom,
                )
                .all()
            )
            if first_visits:
                points = make_grid_points(
                    ((fv.tile_x, fv.tile_y) for fv in first_visits),
                    zoom,
                )
                new_tiles_geojson[zoom] = make_grid_file_geojson(points)
            new_tiles_per_zoom[zoom] = len(first_visits)
            cluster_diff_geojson_urls[zoom] = url_for(
                "explorer.cluster_history_activity_diff",
                zoom=zoom,
                activity_id=activity.id,
            )

        line_color_columns_avail = {
            column.name: column
            for column in TIME_SERIES_COLUMNS
            if column.name in time_series.columns
        }

        context = {
            "activity": activity,
            "color_line_geojson": line_json,
            "progress_marker_geojson": make_geojson_progress_markers_from_time_series(
                time_series,
                eighth_marker_min_distance_km=config.eighth_marker_min_distance_km,
            ),
            "progress_marker_time_geojson": make_geojson_progress_markers_time_based(
                time_series,
                eighth_marker_min_duration_s=config.eighth_marker_min_duration_hours
                * 3600,
            ),
            "similar_activites": similar_activities,
            "new_tiles": new_tiles_per_zoom,
            "new_tiles_geojson": new_tiles_geojson,
            "cluster_diff_geojson_urls": cluster_diff_geojson_urls,
            "show_progress_markers": config.show_progress_markers,
        }

        display_time_series = time_series.copy()
        if activity.iana_timezone and not pd.isna(time_series["time"]).all():
            display_time_series["time"] = (
                time_series["time"]
                .dt.tz_convert(activity.iana_timezone)
                .dt.tz_localize(None)
            )

        if activity.start_local_tz:
            context["date"] = activity.start_local_tz.date()
            context["time"] = activity.start_local_tz.time()

        if not pd.isna(time_series["time"]).all():
            context.update(
                {
                    "distance_time_plot": distance_time_plot(display_time_series),
                    "color_line_geojson": make_geojson_line_segments_with_columns(
                        time_series, tuple(line_color_columns_avail)
                    ),
                    "speed_time_plot": speed_time_plot(display_time_series),
                    "speed_distribution_plot": speed_distribution_plot(
                        display_time_series
                    ),
                    "line_color_column": next(iter(line_color_columns_avail)),
                    "line_color_columns": {
                        name: {
                            "display_name": str(column.display_name),
                            "unit": column.unit,
                            "format": column.format,
                        }
                        for name, column in line_color_columns_avail.items()
                    },
                }
            )

        if (
            heart_zones := _extract_heart_rate_zones(
                time_series, heart_rate_zone_computer
            )
        ) is not None:
            context["heart_zones_plot"] = heart_rate_zone_plot(heart_zones)
        if "elevation" in time_series.columns:
            context["elevation_time_plot"] = elevation_time_plot(display_time_series)
        if "elevation_gain_cum" in time_series.columns:
            context["elevation_gain_cum_plot"] = elevation_gain_cum_plot(
                display_time_series
            )
        if "heartrate" in time_series.columns:
            context["heartrate_time_plot"] = heart_rate_time_plot(display_time_series)
        if "cadence" in time_series.columns:
            context["cadence_time_plot"] = cadence_time_plot(display_time_series)
        if "power" in time_series.columns:
            context["power_time_plot"] = power_time_plot(display_time_series)

        return render_template(
            "activity/show.html.j2",
            **context,
            is_authenticated=authenticator.is_authenticated(),
        )

    @blueprint.route("/<int:id>/line.geojson")
    def geojson_line(id: int) -> ResponseReturnValue:
        return make_geojson_from_time_series(
            DB.session.get_one(Activity, id).time_series,
            config_accessor.ui().eighth_marker_min_distance_km,
        )

    @blueprint.route("/<int:id>/sharepic.png")
    def sharepic(id: int) -> ResponseReturnValue:
        activity = repository.get_activity_by_id(id)
        time_series = repository.get_time_series(id)
        for privacy_zone in DB.session.scalars(sqlalchemy.select(PrivacyZone)).all():
            time_series = privacy_zone.filter_time_series(time_series)
        if len(time_series) == 0:
            time_series = repository.get_time_series(id)
        return Response(
            make_sharepic(
                activity,
                time_series,
                config_accessor.ui().sharepic_suppressed_fields,
                config_accessor.map(),
            ),
            mimetype="image/png",
        )

    @blueprint.route("/day/<int:year>/<int:month>/<int:day>")
    def day(year: int, month: int, day: int) -> ResponseReturnValue:
        meta = repository.meta
        selection = meta["start_local"].dt.date == datetime.date(year, month, day)
        activities_that_day = meta.loc[selection]

        time_series = [
            repository.get_time_series(activity_id)
            for activity_id in activities_that_day["id"]
        ]

        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in ts.groupby("segment_id")
                        ]
                    ),
                    properties={"color": matplotlib.colors.to_hex(cmap(i % 8))},
                )
                for i, ts in enumerate(time_series)
            ]
        )

        activities_list = activities_that_day.to_dict(orient="records")
        for i, activity_record in enumerate(activities_list):
            activity_record["color"] = matplotlib.colors.to_hex(cmap(i % 8))

        context = {
            "activities": activities_list,
            "geojson": geojson.dumps(fc),
            "date": datetime.date(year, month, day).isoformat(),
            "total_distance": activities_that_day["distance_km"].sum(),
            "total_elapsed_time": activities_that_day["elapsed_time"].sum(),
            "day": day,
            "month": month,
            "year": year,
        }
        return render_template(
            "activity/day.html.j2",
            **context,
        )

    @blueprint.route("/day-sharepic/<int:year>/<int:month>/<int:day>/sharepic.png")
    def day_sharepic(year: int, month: int, day: int) -> ResponseReturnValue:
        config = config_accessor.map()
        meta = repository.meta
        selection = meta["start_local"].dt.date == datetime.date(year, month, day)
        activities_that_day = meta.loc[selection]

        time_series = [
            repository.get_time_series(activity_id)
            for activity_id in activities_that_day["id"]
        ]
        assert len(activities_that_day) > 0
        assert len(time_series) > 0
        return Response(
            make_day_sharepic(activities_that_day, time_series, config),
            mimetype="image/png",
        )

    @blueprint.route("/name/<name>")
    def name(name: str) -> ResponseReturnValue:
        meta = repository.meta
        selection = meta["name"] == name
        activities_with_name = meta.loc[selection]

        time_series = [
            repository.get_time_series(activity_id)
            for activity_id in activities_with_name["id"]
        ]

        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in ts.groupby("segment_id")
                        ]
                    ),
                    properties={"color": matplotlib.colors.to_hex(cmap(i % 8))},
                )
                for i, ts in enumerate(time_series)
            ]
        )

        activities_list = activities_with_name.to_dict(orient="records")
        for i, activity_record in enumerate(activities_list):
            activity_record["color"] = matplotlib.colors.to_hex(cmap(i % 8))

        context = {
            "activities": activities_list,
            "geojson": geojson.dumps(fc),
            "name": name,
            "tick_plot": name_tick_plot(activities_with_name),
            "equipment_plot": name_equipment_plot(activities_with_name),
            "distance_plot": name_distance_plot(activities_with_name),
            "minutes_plot": name_minutes_plot(activities_with_name),
        }
        return render_template(
            "activity/name.html.j2",
            **context,
        )

    @blueprint.route("/edit/<id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def edit(id: str) -> ResponseReturnValue:
        activity = DB.session.get(Activity, int(id))
        if activity is None:
            abort(404)
        equipments = DB.session.scalars(sqlalchemy.select(Equipment)).all()
        kinds = DB.session.scalars(sqlalchemy.select(Kind)).all()
        tags = DB.session.scalars(sqlalchemy.select(Tag)).all()

        if request.method == "POST":
            activity.name = request.form.get("name")
            activity.description = request.form.get("description") or None

            previous_start = activity.start
            start_changed = False
            form_start = request.form.get("start")
            if form_start:
                try:
                    naive_local = datetime.datetime.fromisoformat(form_start)
                except ValueError:
                    flash(_("Could not parse start time."), category="danger")
                    return redirect(url_for(".edit", id=activity.id))
                tz_name = activity.iana_timezone or "UTC"
                local_dt = naive_local.replace(tzinfo=zoneinfo.ZoneInfo(tz_name))
                activity.start = local_dt.astimezone(zoneinfo.ZoneInfo("UTC")).replace(
                    tzinfo=None
                )
                start_changed = activity.start != previous_start

            form_equipment = request.form.get("equipment")
            if form_equipment and form_equipment != "null":
                activity.equipment = DB.session.get_one(Equipment, int(form_equipment))
            else:
                activity.equipment = get_or_make_equipment(DEFAULT_UNKNOWN_NAME)

            form_kind = request.form.get("kind")
            if form_kind and form_kind != "null":
                activity.kind = DB.session.get_one(Kind, int(form_kind))
            else:
                activity.kind = get_or_make_kind(DEFAULT_UNKNOWN_NAME)

            form_tags = request.form.getlist("tag")
            activity.tags = [
                DB.session.get_one(Tag, int(tag_id_str)) for tag_id_str in form_tags
            ]

            DB.session.commit()
            if start_changed:
                refresh_tile_visits_for_activity(activity.id)
            return redirect(url_for(".show", id=activity.id))

        return render_template(
            "activity/edit.html.j2",
            activity=activity,
            kinds=kinds,
            equipments=equipments,
            tags=tags,
        )

    @blueprint.route("/trim/<id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def trim(id: str) -> ResponseReturnValue:
        config = config_accessor.activity_import()
        activity = DB.session.get(Activity, int(id))
        if activity is None:
            abort(404)

        if request.method == "POST":
            form_begin = request.form.get("begin")
            form_end = request.form.get("end")

            if form_begin:
                activity.index_begin = int(form_begin)
            else:
                activity.index_begin = None
            if form_end:
                activity.index_end = int(form_end)
            else:
                activity.index_end = None

            raw_time_series = activity.raw_time_series
            update_and_commit(activity, raw_time_series, config, force=True)

        cmap = matplotlib.colormaps["turbo"]
        num_points = max(len(activity.raw_time_series), 1)
        begin = activity.index_begin or 0
        end = activity.index_end or num_points

        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.LineString(
                        [
                            (lon, lat)
                            for lat, lon in zip(group["latitude"], group["longitude"])
                        ]
                    )
                )
                for _, group in activity.raw_time_series.groupby("segment_id")
            ]
            + [
                geojson.Feature(
                    geometry=geojson.Point(
                        (lon, lat),
                    ),
                    properties={
                        "name": f"{index}",
                        "markerType": "circle",
                        "markerStyle": {
                            "fillColor": matplotlib.colors.to_hex(
                                cmap(1 - index / num_points)
                            ),
                            "fillOpacity": 0.5,
                            "radius": 8,
                            "color": "black" if begin <= index < end else "white",
                            "opacity": 0.8,
                            "weight": 2,
                        },
                    },
                )
                for _, group in activity.raw_time_series.groupby("segment_id")
                for index, lat, lon in zip(
                    group.index, group["latitude"], group["longitude"]
                )
            ]
        )
        return render_template(
            "activity/trim.html.j2",
            activity=activity,
            color_line_geojson=geojson.dumps(fc),
        )

    @blueprint.route("/<int:id>/reenrich", methods=["POST"])
    @needs_authentication(authenticator)
    def reenrich(id: int) -> ResponseReturnValue:
        config = config_accessor.activity_import()
        activity = DB.session.get(Activity, id)
        if activity is None:
            abort(404)
        update_and_commit(activity, activity.raw_time_series, config, force=True)
        flash(_("Activity has been re-enriched."), category="success")
        return redirect(url_for(".show", id=id))

    @blueprint.route("/delete/<id>")
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        activity = DB.session.get_one(Activity, id)
        activity.delete_data()
        DB.session.delete(activity)
        DB.session.commit()
        remove_activity_from_tile_state(id)
        return redirect(url_for("index"))

    @blueprint.route("/download-original/<id>")
    @needs_authentication(authenticator)
    def download_original(id: int) -> ResponseReturnValue:
        activity = DB.session.get_one(Activity, id)
        path = pathlib.Path(activity.path)
        with open(path, "rb") as f:
            return Response(
                f.read(),
                mimetype="application/octet-stream",
                headers={"Content-disposition": f'attachment; filename="{path.name}"'},
            )

    return blueprint


def speed_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Speed"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("speed", title=_("Speed / km/h")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def speed_distribution_plot(time_series: pd.DataFrame) -> str:
    df = pd.DataFrame(
        {
            "speed": time_series["speed"],
            "step": time_series["time"].diff().dt.total_seconds() / 60,
        }
    ).dropna()
    return (
        alt.Chart(df.loc[df["speed"] > 0], title=_("Speed distribution"))
        .mark_bar()
        .encode(
            alt.X("speed", bin=alt.Bin(step=5), title=_("Speed / km/h")),
            alt.Y("sum(step)", title=_("Duration / min")),
        )
        .to_json(format="vega")
    )


def distance_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Distance"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("distance_km", title=_("Distance / km")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive()
        .to_json(format="vega")
    )


def elevation_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Elevation"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y(
                "elevation",
                scale=alt.Scale(zero=False),
                title=_("Elevation / m"),
            ),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def elevation_gain_cum_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Elevation Gain"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y(
                "elevation_gain_cum",
                scale=alt.Scale(zero=False),
                title=_("Elevation gain / m"),
            ),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def heart_rate_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Heart Rate"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("heartrate", scale=alt.Scale(zero=False), title=_("Heart rate")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def cadence_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Cadence"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("cadence", title=_("Cadence")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def power_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title=_("Power"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("power", scale=alt.Scale(zero=False), title=_("Power / W")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def heart_rate_zone_plot(heart_zones: pd.DataFrame) -> str:
    return (
        alt.Chart(heart_zones, title=_("Heart Rate Zones"))
        .mark_bar()
        .encode(
            alt.X("minutes", title=_("Duration / min")),
            alt.Y("heartzone:O", title=_("Zone")),
            alt.Color("heartzone:O", scale=alt.Scale(scheme="turbo"), title=_("Zone")),
        )
        .to_json(format="vega")
    )


def name_tick_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title=_("Repetitions"))
        .mark_tick()
        .encode(
            alt.X("start_local", title=_("Date")),
        )
        .to_json(format="vega")
    )


def name_equipment_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title=_("Equipment"))
        .mark_bar()
        .encode(
            alt.X("count()", title=_("Count")), alt.Y("equipment", title=_("Equipment"))
        )
        .to_json(format="vega")
    )


def name_distance_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title=_("Distance"))
        .mark_bar()
        .encode(
            alt.X("distance_km", bin=True, title=_("Distance / km")),
            alt.Y("count()", title=_("Count")),
        )
        .to_json(format="vega")
    )


def name_minutes_plot(meta: pd.DataFrame) -> str:
    minutes = meta["elapsed_time"].dt.total_seconds() / 60
    return (
        alt.Chart(pd.DataFrame({"minutes": minutes}), title=_("Elapsed time"))
        .mark_bar()
        .encode(
            alt.X("minutes", bin=True, title=_("Time / min")),
            alt.Y("count()", title=_("Count")),
        )
        .to_json(format="vega")
    )


_SHAREPIC_FOOTER_HEIGHT = 115
_SHAREPIC_HEADER_HEIGHT = 50
_FONT_CANDIDATES = [
    "/usr/share/fonts/open-sans/OpenSans-Regular.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
    "/usr/share/fonts/adwaita-sans-fonts/AdwaitaSans-Regular.ttf",
]
_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/open-sans/OpenSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
]


def _get_font(
    size: int, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES
    for path in candidates:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def make_sharepic_base(time_series_list: list[pd.DataFrame], config: MapConfig):
    all_time_series = pd.concat(time_series_list)
    finite_mask = np.isfinite(all_time_series["x"]) & np.isfinite(all_time_series["y"])
    all_time_series = all_time_series.loc[finite_mask]

    target_width = 600
    target_height = 600
    footer_height = _SHAREPIC_FOOTER_HEIGHT
    header_height = _SHAREPIC_HEADER_HEIGHT
    target_map_height = target_height - footer_height - header_height

    if len(all_time_series) == 0:
        return Image.new("RGB", (target_width, target_height), "black")

    tile_x = all_time_series["x"]
    tile_y = all_time_series["y"]
    tile_width = tile_x.max() - tile_x.min()
    tile_height = tile_y.max() - tile_y.min()

    zoom_candidates = [OSM_MAX_ZOOM]
    if tile_width > 0:
        zoom_candidates.append(np.log2(target_width / tile_width / OSM_TILE_SIZE))
    if tile_height > 0:
        zoom_candidates.append(np.log2(target_map_height / tile_height / OSM_TILE_SIZE))
    zoom_float = min(zoom_candidates)
    zoom = int(np.clip(np.floor(zoom_float), 0, OSM_MAX_ZOOM))

    tile_xz = tile_x * 2**zoom
    tile_yz = tile_y * 2**zoom

    tile_xz_center = (
        (tile_xz.max() + tile_xz.min()) / 2,
        (tile_yz.max() + tile_yz.min()) / 2,
    )

    tile_bounds = tile_bounds_around_center(
        tile_xz_center, (target_width, target_map_height), zoom
    )
    tile_bounds.y1 -= header_height / OSM_TILE_SIZE
    tile_bounds.y2 += footer_height / OSM_TILE_SIZE
    background = map_image_from_tile_bounds(tile_bounds, config)

    img = Image.fromarray((background * 255).astype("uint8"), "RGB")
    draw = ImageDraw.Draw(img, mode="RGBA")

    map_center_y = header_height + target_map_height / 2

    for time_series in time_series_list:
        time_series = time_series.loc[
            np.isfinite(time_series["x"]) & np.isfinite(time_series["y"])
        ]
        if len(time_series) == 0:
            continue
        for _index, group in time_series.groupby("segment_id"):
            tile_xz = group["x"] * 2**zoom
            tile_yz = group["y"] * 2**zoom
            xy = list(
                zip(
                    (tile_xz - tile_xz_center[0]) * OSM_TILE_SIZE + target_width / 2,
                    (tile_yz - tile_xz_center[1]) * OSM_TILE_SIZE + map_center_y,
                )
            )
            draw.line(xy, fill=(255, 255, 255, 120), width=7)
            draw.line(xy, fill=(220, 50, 30), width=4)

    return img


def _draw_sharepic_stats(
    draw: ImageDraw.ImageDraw,
    img_width: int,
    footer_y: int,
    stat_items: list[tuple[str, str]],
) -> None:
    if not stat_items:
        return
    n = len(stat_items)
    col_w = img_width // n
    stat_y = footer_y + 42
    for i, (value, label) in enumerate(stat_items):
        x_center = i * col_w + col_w // 2
        draw.text(
            (x_center, stat_y),
            value,
            fill="white",
            font=_get_font(22, bold=True),
            anchor="mt",
        )
        draw.text(
            (x_center, stat_y + 28),
            label,
            fill=(140, 140, 140),
            font=_get_font(11),
            anchor="mt",
        )


def make_sharepic(
    activity: Activity,
    time_series: pd.DataFrame,
    sharepic_suppressed_fields: list[str],
    config: MapConfig,
) -> bytes:
    img = make_sharepic_base([time_series], config)
    draw = ImageDraw.Draw(img, mode="RGBA")

    # Header overlay: activity name
    draw.rectangle([0, 0, img.width, _SHAREPIC_HEADER_HEIGHT], fill=(10, 10, 10, 210))
    name = activity.name or ""
    draw.text(
        (16, (_SHAREPIC_HEADER_HEIGHT - 26) // 2),
        name,
        fill="white",
        font=_get_font(24, bold=True),
    )

    # Footer overlay
    footer_y = img.height - _SHAREPIC_FOOTER_HEIGHT
    draw.rectangle([0, footer_y, img.width, img.height], fill=(10, 10, 10, 215))

    # Secondary meta line: date · kind · equipment
    meta_parts = []
    if activity.start_local_tz and "start" not in sharepic_suppressed_fields:
        meta_parts.append(str(activity.start_local_tz.date()))
    if activity.kind and "kind" not in sharepic_suppressed_fields:
        meta_parts.append(activity.kind.name)
    if activity.equipment and "equipment" not in sharepic_suppressed_fields:
        meta_parts.append(activity.equipment.name)
    if meta_parts:
        draw.text(
            (16, footer_y + 12),
            "  ·  ".join(meta_parts),
            fill=(170, 170, 170),
            font=_get_font(14),
        )

    # Stats columns
    stat_items = []
    if "distance_km" not in sharepic_suppressed_fields:
        stat_items.append((f"{activity.distance_km:.1f} km", "DISTANCE"))
    if activity.elapsed_time and "elapsed_time" not in sharepic_suppressed_fields:
        stat_items.append((_format_elapsed_time(activity.elapsed_time), "DURATION"))
    if activity.calories and "calories" not in sharepic_suppressed_fields:
        stat_items.append((f"{activity.calories}", "KCAL"))
    if activity.steps and "steps" not in sharepic_suppressed_fields:
        stat_items.append((f"{activity.steps}", "STEPS"))
    _draw_sharepic_stats(draw, img.width, footer_y, stat_items)

    draw.text(
        (img.width - 8, img.height - 6),
        "Map: © OpenStreetMap Contributors",
        fill=(90, 90, 90),
        font=_get_font(11),
        anchor="rs",
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def make_day_sharepic(
    activities: pd.DataFrame,
    time_series_list: list[pd.DataFrame],
    config: MapConfig,
) -> bytes:
    img = make_sharepic_base(time_series_list, config)
    draw = ImageDraw.Draw(img, mode="RGBA")

    date = activities.iloc[0]["start_local"].date()
    distance_km = activities["distance_km"].sum()
    elapsed_time: pd.Timedelta = activities["elapsed_time"].sum()

    # Header: date
    draw.rectangle([0, 0, img.width, _SHAREPIC_HEADER_HEIGHT], fill=(10, 10, 10, 210))
    draw.text(
        (16, (_SHAREPIC_HEADER_HEIGHT - 26) // 2),
        str(date),
        fill="white",
        font=_get_font(24, bold=True),
    )

    # Footer overlay
    footer_y = img.height - _SHAREPIC_FOOTER_HEIGHT
    draw.rectangle([0, footer_y, img.width, img.height], fill=(10, 10, 10, 215))

    n_activities = len(activities)
    activity_label = (
        f"{n_activities} {'activity' if n_activities == 1 else 'activities'}"
    )
    draw.text(
        (16, footer_y + 12), activity_label, fill=(170, 170, 170), font=_get_font(14)
    )

    stat_items = [
        (f"{distance_km:.1f} km", "DISTANCE"),
        (_format_elapsed_time(elapsed_time), "DURATION"),
    ]
    _draw_sharepic_stats(draw, img.width, footer_y, stat_items)

    draw.text(
        (img.width - 8, img.height - 6),
        "Map: © OpenStreetMap Contributors",
        fill=(90, 90, 90),
        font=_get_font(11),
        anchor="rs",
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def _format_elapsed_time(elapsed_time: datetime.timedelta | pd.Timedelta) -> str:
    rounded_seconds = round(pd.Timedelta(elapsed_time).total_seconds())
    rounded = datetime.timedelta(seconds=rounded_seconds)
    return re.sub(r"^0 days,? ", "", f"{rounded}")


def _extract_heart_rate_zones(
    time_series: pd.DataFrame, heart_rate_zone_computer: HeartRateZoneComputer
) -> pd.DataFrame | None:
    if "heartrate" not in time_series:
        return

    try:
        zones = heart_rate_zone_computer.compute_zones(
            time_series["heartrate"], time_series["time"].iloc[0].year
        )
    except RuntimeError:
        return

    df = pd.DataFrame({"heartzone": zones, "step": time_series["time"].diff()}).dropna()
    duration_per_zone = df.groupby("heartzone").sum()["step"].dt.total_seconds() / 60
    duration_per_zone.name = "minutes"
    for i in range(6):
        if i not in duration_per_zone:
            duration_per_zone.loc[i] = 0.0
    result = duration_per_zone.reset_index()
    return result
