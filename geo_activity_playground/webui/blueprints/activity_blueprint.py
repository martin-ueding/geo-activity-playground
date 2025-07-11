import datetime
import io
import logging
import pathlib
import re
from typing import Optional

import altair as alt
import geojson
import matplotlib
import numpy as np
import pandas as pd
import sqlalchemy
from flask import abort
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for
from flask.typing import ResponseReturnValue
from PIL import Image
from PIL import ImageDraw

from ...core.activities import ActivityRepository
from ...core.activities import make_color_bar
from ...core.activities import make_geojson_color_line
from ...core.activities import make_geojson_from_time_series
from ...core.config import Config
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.datamodel import Equipment
from ...core.datamodel import Kind
from ...core.datamodel import Tag
from ...core.enrichment import update_and_commit
from ...core.heart_rate import HeartRateZoneComputer
from ...core.privacy_zones import PrivacyZone
from ...core.raster_map import map_image_from_tile_bounds
from ...core.raster_map import OSM_MAX_ZOOM
from ...core.raster_map import OSM_TILE_SIZE
from ...core.raster_map import tile_bounds_around_center
from ...explorer.grid_file import make_grid_file_geojson
from ...explorer.grid_file import make_grid_points
from ...explorer.tile_visits import TileVisitAccessor
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..columns import TIME_SERIES_COLUMNS

logger = logging.getLogger(__name__)


def make_activity_blueprint(
    repository: ActivityRepository,
    authenticator: Authenticator,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
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
        activity = repository.get_activity_by_id(id)

        time_series = repository.get_time_series(id)
        line_json = make_geojson_from_time_series(time_series)

        meta = repository.meta
        similar_activities = meta.loc[
            (meta.name == activity.name) & (meta.id != activity.id)
        ]
        similar_activities = [row for _, row in similar_activities.iterrows()]
        similar_activities.reverse()

        new_tiles = {
            zoom: sum(
                tile_visit_accessor.tile_state["tile_history"][zoom]["activity_id"]
                == activity.id
            )
            for zoom in sorted(config.explorer_zoom_levels)
            if not tile_visit_accessor.tile_state["tile_history"][zoom].empty
        }

        new_tiles_geojson = {}
        new_tiles_per_zoom = {}
        for zoom in sorted(config.explorer_zoom_levels):
            if tile_visit_accessor.tile_state["tile_history"][zoom].empty:
                continue
            new_tiles = tile_visit_accessor.tile_state["tile_history"][zoom].loc[
                tile_visit_accessor.tile_state["tile_history"][zoom]["activity_id"]
                == activity.id
            ]
            if len(new_tiles):
                points = make_grid_points(
                    (
                        (row["tile_x"], row["tile_y"])
                        for index, row in new_tiles.iterrows()
                    ),
                    zoom,
                )
                new_tiles_geojson[zoom] = make_grid_file_geojson(points)
            new_tiles_per_zoom[zoom] = len(new_tiles)

        line_color_columns_avail = dict(
            [(column.name, column) for column in TIME_SERIES_COLUMNS]
        )
        line_color_column = (
            request.args.get("line_color_column")
            or next(iter(line_color_columns_avail.values())).name
        )

        context = {
            "activity": activity,
            "color_line_geojson": line_json,
            "similar_activites": similar_activities,
            "new_tiles": new_tiles_per_zoom,
            "new_tiles_geojson": new_tiles_geojson,
        }

        if not pd.isna(time_series["time"]).all():
            context.update(
                {
                    "distance_time_plot": distance_time_plot(time_series),
                    "color_line_geojson": make_geojson_color_line(
                        time_series, line_color_column
                    ),
                    "speed_time_plot": speed_time_plot(time_series),
                    "speed_distribution_plot": speed_distribution_plot(time_series),
                    "line_color_bar": make_color_bar(
                        time_series[line_color_column],
                        line_color_columns_avail[line_color_column].format,
                    ),
                    "date": activity.start_local_tz.date(),
                    "time": activity.start_local_tz.time(),
                    "line_color_column": line_color_column,
                    "line_color_columns_avail": line_color_columns_avail,
                }
            )

        if (
            heart_zones := _extract_heart_rate_zones(
                time_series, heart_rate_zone_computer
            )
        ) is not None:
            context["heart_zones_plot"] = heart_rate_zone_plot(heart_zones)
        if "elevation" in time_series.columns:
            context["elevation_time_plot"] = elevation_time_plot(time_series)
        if "elevation_gain_cum" in time_series.columns:
            context["elevation_gain_cum_plot"] = elevation_gain_cum_plot(time_series)
        if "heartrate" in time_series.columns:
            context["heartrate_time_plot"] = heart_rate_time_plot(time_series)
        if "cadence" in time_series.columns:
            context["cadence_time_plot"] = cadence_time_plot(time_series)

        return render_template("activity/show.html.j2", **context)

    @blueprint.route("/<int:id>/sharepic.png")
    def sharepic(id: int) -> ResponseReturnValue:
        activity = repository.get_activity_by_id(id)
        time_series = repository.get_time_series(id)
        for coordinates in config.privacy_zones.values():
            privacy_zone = PrivacyZone(coordinates)
            time_series = privacy_zone.filter_time_series(time_series)
        if len(time_series) == 0:
            time_series = repository.get_time_series(id)
        return Response(
            make_sharepic(
                activity, time_series, config.sharepic_suppressed_fields, config
            ),
            mimetype="image/png",
        )

    @blueprint.route("/day/<int:year>/<int:month>/<int:day>")
    def day(year: int, month: int, day: int) -> ResponseReturnValue:
        meta = repository.meta
        selection = meta["start"].dt.date == datetime.date(year, month, day)
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
        meta = repository.meta
        selection = meta["start"].dt.date == datetime.date(year, month, day)
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

            form_equipment = request.form.get("equipment")
            if form_equipment == "null":
                activity.equipment = None
            else:
                activity.equipment = DB.session.get_one(Equipment, int(form_equipment))

            form_kind = request.form.get("kind")
            if form_kind == "null":
                activity.kind = None
            else:
                activity.kind = DB.session.get_one(Kind, int(form_kind))

            form_tags = request.form.getlist("tag")
            activity.tags = [
                DB.session.get_one(Tag, int(tag_id_str)) for tag_id_str in form_tags
            ]

            DB.session.commit()
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
        activity = DB.session.get(Activity, int(id))
        if activity is None:
            abort(404)

        if request.method == "POST":
            form_begin = request.form.get("begin")
            form_end = request.form.get("end")

            if form_begin:
                activity.index_begin = int(form_begin)
            if form_end:
                activity.index_end = int(form_end)

            time_series = activity.time_series
            update_and_commit(activity, time_series, config)

        cmap = matplotlib.colormaps["turbo"]
        num_points = len(activity.time_series)
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

    @blueprint.route("/delete/<id>")
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        activity = DB.session.get_one(Activity, id)
        activity.delete_data()
        DB.session.delete(activity)
        DB.session.commit()
        return redirect(url_for("index"))

    @blueprint.route("/download-original/<id>")
    @needs_authentication(authenticator)
    def download_original(id: int) -> ResponseReturnValue:
        activity = DB.session.get_one(Activity, id)
        path = pathlib.Path(activity.path)
        with open(path) as f:
            return Response(
                f.read(),
                mimetype="application/octet-stream",
                headers={"Content-disposition": f'attachment; filename="{path.name}"'},
            )

    return blueprint


def speed_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Speed")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("speed", title="Speed / km/h"),
            alt.Color("segment_id:N", title="Segment"),
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
        alt.Chart(df.loc[df["speed"] > 0], title="Speed distribution")
        .mark_bar()
        .encode(
            alt.X("speed", bin=alt.Bin(step=5), title="Speed / km/h"),
            alt.Y("sum(step)", title="Duration / min"),
        )
        .to_json(format="vega")
    )


def distance_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Distance")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive()
        .to_json(format="vega")
    )


def elevation_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Elevation")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y(
                "elevation",
                scale=alt.Scale(zero=False),
                title="Elevation / m",
            ),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def elevation_gain_cum_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Elevation Gain")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y(
                "elevation_gain_cum",
                scale=alt.Scale(zero=False),
                title="Elevation gain / m",
            ),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def heart_rate_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Heart Rate")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("heartrate", scale=alt.Scale(zero=False), title="Heart rate"),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def cadence_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Cadence")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("cadence", title="Cadence"),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def heart_rate_zone_plot(heart_zones: pd.DataFrame) -> str:
    return (
        alt.Chart(heart_zones, title="Heart Rate Zones")
        .mark_bar()
        .encode(
            alt.X("minutes", title="Duration / min"),
            alt.Y("heartzone:O", title="Zone"),
            alt.Color("heartzone:O", scale=alt.Scale(scheme="turbo"), title="Zone"),
        )
        .to_json(format="vega")
    )


def name_tick_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Repetitions")
        .mark_tick()
        .encode(
            alt.X("start", title="Date"),
        )
        .to_json(format="vega")
    )


def name_equipment_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Equipment")
        .mark_bar()
        .encode(alt.X("count()", title="Count"), alt.Y("equipment", title="Equipment"))
        .to_json(format="vega")
    )


def name_distance_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Distance")
        .mark_bar()
        .encode(
            alt.X("distance_km", bin=True, title="Distance / km"),
            alt.Y("count()", title="Count"),
        )
        .to_json(format="vega")
    )


def name_minutes_plot(meta: pd.DataFrame) -> str:
    minutes = meta["elapsed_time"].dt.total_seconds() / 60
    return (
        alt.Chart(pd.DataFrame({"minutes": minutes}), title="Elapsed time")
        .mark_bar()
        .encode(
            alt.X("minutes", bin=True, title="Time / min"),
            alt.Y("count()", title="Count"),
        )
        .to_json(format="vega")
    )


def make_sharepic_base(time_series_list: list[pd.DataFrame], config: Config):
    all_time_series = pd.concat(time_series_list)
    tile_x = all_time_series["x"]
    tile_y = all_time_series["y"]
    tile_width = tile_x.max() - tile_x.min()
    tile_height = tile_y.max() - tile_y.min()

    target_width = 600
    target_height = 600
    footer_height = 100
    target_map_height = target_height - footer_height

    zoom = int(
        min(
            np.log2(target_width / tile_width / OSM_TILE_SIZE),
            np.log2(target_map_height / tile_height / OSM_TILE_SIZE),
            OSM_MAX_ZOOM,
        )
    )

    tile_xz = tile_x * 2**zoom
    tile_yz = tile_y * 2**zoom

    tile_xz_center = (
        (tile_xz.max() + tile_xz.min()) / 2,
        (tile_yz.max() + tile_yz.min()) / 2,
    )

    tile_bounds = tile_bounds_around_center(
        tile_xz_center, (target_width, target_height - footer_height), zoom
    )
    tile_bounds.y2 += footer_height / OSM_TILE_SIZE
    background = map_image_from_tile_bounds(tile_bounds, config)

    img = Image.fromarray((background * 255).astype("uint8"), "RGB")
    draw = ImageDraw.Draw(img, mode="RGBA")

    for time_series in time_series_list:
        for _, group in time_series.groupby("segment_id"):
            yx = list(
                zip(
                    (tile_xz - tile_xz_center[0]) * OSM_TILE_SIZE + target_width / 2,
                    (tile_yz - tile_xz_center[1]) * OSM_TILE_SIZE
                    + target_map_height / 2,
                )
            )

            draw.line(yx, fill="red", width=4)

    return img


def make_sharepic(
    activity: Activity,
    time_series: pd.DataFrame,
    sharepic_suppressed_fields: list[str],
    config: Config,
) -> bytes:
    footer_height = 100

    img = make_sharepic_base([time_series], config)

    draw = ImageDraw.Draw(img, mode="RGBA")
    draw.rectangle(
        [0, img.height - footer_height, img.width, img.height], fill=(0, 0, 0, 180)
    )

    facts = {
        "distance_km": f"\n{activity.distance_km:.1f} km",
    }
    if activity.start:
        facts["start"] = f"{activity.start.date()}"
    if activity.elapsed_time:
        facts["elapsed_time"] = re.sub(r"^0 days ", "", f"{activity.elapsed_time}")
    if activity.kind:
        facts["kind"] = f"{activity.kind.name}"
    if activity.equipment:
        facts["equipment"] = f"{activity.equipment.name}"

    if activity.calories:
        facts["calories"] = f"{activity.calories} kcal"
    if activity.steps:
        facts["steps"] = f"{activity.steps} steps"

    facts = {
        key: value
        for key, value in facts.items()
        if not key in sharepic_suppressed_fields
    }

    draw.text(
        (35, img.height - footer_height + 10),
        "      ".join(facts.values()),
        font_size=20,
    )

    draw.text(
        (img.width - 250, img.height - 20),
        "Map: © Open Street Map Contributors",
        font_size=14,
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def make_day_sharepic(
    activities: pd.DataFrame,
    time_series_list: list[pd.DataFrame],
    config: Config,
) -> bytes:
    footer_height = 100

    img = make_sharepic_base(time_series_list, config)

    draw = ImageDraw.Draw(img, mode="RGBA")
    draw.rectangle(
        [0, img.height - footer_height, img.width, img.height], fill=(0, 0, 0, 180)
    )

    date = activities.iloc[0]["start"].date()
    distance_km = activities["distance_km"].sum()
    elapsed_time: pd.Timedelta = activities["elapsed_time"].sum()
    elapsed_time = elapsed_time.round("s")

    facts = {
        "date": f"{date}",
        "distance_km": f"{distance_km:.1f} km",
        "elapsed_time": re.sub(r"^0 days ", "", f"{elapsed_time}"),
    }

    draw.text(
        (35, img.height - footer_height + 10),
        "      ".join(facts.values()),
        font_size=20,
    )

    draw.text(
        (img.width - 250, img.height - 20),
        "Map: © Open Street Map Contributors",
        font_size=14,
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def _extract_heart_rate_zones(
    time_series: pd.DataFrame, heart_rate_zone_computer: HeartRateZoneComputer
) -> Optional[pd.DataFrame]:
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
