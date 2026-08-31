import datetime
import logging
import pathlib
import zoneinfo

import altair as alt
import geojson
import matplotlib
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

from ...core.activities import (
    make_geojson_from_time_series,
    make_geojson_line_segments_with_columns,
    make_geojson_progress_markers_from_time_series,
    make_geojson_progress_markers_time_based,
)
from ...core.config import ConfigAccessor
from ...core.datamodel import (
    DB,
    Activity,
    Equipment,
    Kind,
    Tag,
    apply_privacy_zones_to_tracks_if_enabled,
    get_activity_by_id,
    get_time_series,
    iter_activities,
    materialize_metadata,
    query_activity_meta,
    resolved_equipment_without_user,
    resolved_kind_without_user,
    resolved_name_without_user,
    stem_of_path,
)
from ...core.enrichment import update_and_commit
from ...core.grid import geojson_bounding_box_for_tile_collection
from ...core.heart_rate import HeartRateZoneComputer
from ...core.import_exclusion import record_exclusion
from ...core.scan import source_for_activity
from ...core.tile_visits import (
    get_first_visits_for_activity,
    refresh_tile_visits_for_activity,
    remove_activity_from_tile_state,
)
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.columns import TIME_SERIES_COLUMNS
from ...webui.plot_util import to_vega
from ..explorer.clustering import get_cluster_tiles_gained_by_activity
from ..explorer.model import TileStyleName, get_tile_styles

logger = logging.getLogger(__name__)


def apply_metadata(
    activity: Activity,
    name: str | None,
    description: str | None,
    equipment_id: str | None,
    kind_id: str | None,
    tag_ids: list[str],
) -> None:
    """Store the form values as the user layer and materialize the result.

    A submitted value that merely repeats what the file and path layers already yield
    is not recorded as an override, so that simply opening the edit form does not pin
    an activity against future re-imports and regex changes.
    """
    activity.description = description or None

    activity.name_from_user = (
        name if name and name != resolved_name_without_user(activity) else None
    )

    equipment = (
        DB.session.get_one(Equipment, int(equipment_id))
        if equipment_id and equipment_id != "null"
        else None
    )
    activity.equipment_from_user = (
        equipment
        if equipment is not None
        and equipment.name != resolved_equipment_without_user(activity).name
        else None
    )

    kind = (
        DB.session.get_one(Kind, int(kind_id))
        if kind_id and kind_id != "null"
        else None
    )
    activity.kind_from_user = (
        kind
        if kind is not None and kind.name != resolved_kind_without_user(activity).name
        else None
    )

    materialize_metadata(activity)

    activity.tags = [DB.session.get_one(Tag, int(tag_id)) for tag_id in tag_ids]


def metadata_candidates(activity: Activity) -> dict[str, str | None]:
    """Name and kind as the file states them versus as the path yields them."""
    return {
        "name_from_file": activity.name_from_file,
        "name_from_path": activity.name_from_path or stem_of_path(activity.path),
        "kind_from_file": activity.kind_from_file,
        "kind_from_path": activity.kind_from_path,
    }


def make_activity_blueprint(
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
    heart_rate_zone_computer: HeartRateZoneComputer,
) -> Blueprint:
    blueprint = Blueprint("activity", __name__, template_folder="templates")

    @blueprint.route("/all")
    def all() -> ResponseReturnValue:
        ui_config = config_accessor.ui()
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
                            for _, group in apply_privacy_zones_to_tracks_if_enabled(
                                get_time_series(activity.id), ui_config
                            ).groupby("segment_id")
                        ]
                    ),
                    properties={
                        "color": matplotlib.colors.to_hex(cmap(i % 8)),
                        "activity_name": activity.name,
                        "activity_id": str(activity.id),
                    },
                )
                for i, activity in enumerate(iter_activities())
            ]
        )

        context = {
            "geojson": geojson.dumps(fc),
        }
        return render_template("activity/lines.html.j2", **context)

    @blueprint.route("/<int:id>")
    def show(id: str) -> ResponseReturnValue:
        config = config_accessor.ui()
        tile_styles = get_tile_styles()
        activity = get_activity_by_id(id)

        time_series = apply_privacy_zones_to_tracks_if_enabled(
            get_time_series(id), config
        )
        line_json = make_geojson_from_time_series(
            time_series, config.eighth_marker_min_distance_km
        )

        meta = query_activity_meta()
        similar_activities = meta.loc[
            (meta.name == activity.name) & (meta.id != activity.id)
        ]
        similar_activities = [row for _, row in similar_activities.iterrows()]
        similar_activities.reverse()

        # What this activity changed about the explorer tiles, per zoom level.
        new_tile_stats = {}
        new_tiles_bbox = {}
        new_tiles_per_zoom = {}
        for zoom in sorted(config.explorer_zoom_levels):
            new_tiles = {
                (tile_visit.tile_x, tile_visit.tile_y)
                for tile_visit in get_first_visits_for_activity(activity.id, zoom)
            }
            cluster_gained = get_cluster_tiles_gained_by_activity(zoom, activity.id)
            new_tiles_per_zoom[zoom] = len(new_tiles)
            affected = new_tiles | cluster_gained
            if affected:
                new_tile_stats[zoom] = {
                    "new": len(new_tiles - cluster_gained),
                    "cluster": len(cluster_gained - new_tiles),
                    "both": len(new_tiles & cluster_gained),
                }
                new_tiles_bbox[zoom] = geojson_bounding_box_for_tile_collection(
                    sorted(affected), zoom
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
            "new_tile_stats": new_tile_stats,
            "new_tiles_bbox": new_tiles_bbox,
            "new_tile_color": tile_styles[TileStyleName.NEW_TILE].border_color,
            "new_cluster_color": tile_styles[
                TileStyleName.VISITED_NEW_CLUSTER
            ].border_color,
            "new_tile_new_cluster_color": tile_styles[
                TileStyleName.NEW_TILE_NEW_CLUSTER
            ].border_color,
            "show_progress_markers": config.show_progress_markers,
            "activity_line_color": config.activity_line_color,
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
        ui_config = config_accessor.ui()
        return make_geojson_from_time_series(
            apply_privacy_zones_to_tracks_if_enabled(
                DB.session.get_one(Activity, id).time_series, ui_config
            ),
            ui_config.eighth_marker_min_distance_km,
        )

    @blueprint.route("/name/<name>")
    def name(name: str) -> ResponseReturnValue:
        meta = query_activity_meta()
        selection = meta["name"] == name
        activities_with_name = meta.loc[selection]

        ui_config = config_accessor.ui()
        time_series = [
            apply_privacy_zones_to_tracks_if_enabled(
                get_time_series(activity_id), ui_config
            )
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
            apply_metadata(
                activity,
                request.form.get("name"),
                request.form.get("description"),
                request.form.get("equipment"),
                request.form.get("kind"),
                request.form.getlist("tag"),
            )

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

    @blueprint.route("/bulk-edit", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def bulk_edit() -> ResponseReturnValue:
        ids = request.args.getlist("id")
        activities = [
            activity
            for activity in (DB.session.get(Activity, int(id)) for id in ids)
            if activity is not None
        ]

        if request.method == "POST":
            for activity in activities:
                apply_metadata(
                    activity,
                    request.form.get(f"name-{activity.id}"),
                    request.form.get(f"description-{activity.id}"),
                    request.form.get(f"equipment-{activity.id}"),
                    request.form.get(f"kind-{activity.id}"),
                    request.form.getlist(f"tag-{activity.id}"),
                )
            DB.session.commit()
            flash(
                _("Updated %(count)s activities.") % {"count": len(activities)},
                category="success",
            )
            return redirect(url_for(".bulk_edit", id=ids))

        return render_template(
            "activity/bulk-edit.html.j2",
            rows=[
                {"activity": activity, **metadata_candidates(activity)}
                for activity in activities
            ],
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

    @blueprint.route("/<int:id>/reimport", methods=["POST"])
    @needs_authentication(authenticator)
    def reimport(id: int) -> ResponseReturnValue:
        activity = DB.session.get(Activity, id)
        if activity is None:
            abort(404)
        source = source_for_activity(activity)
        if source is None or not source.reingest(activity, config_accessor):
            flash(
                _(
                    "This activity could not be re-imported because its source data is not available."
                ),
                category="warning",
            )
        else:
            refresh_tile_visits_for_activity(activity.id)
            flash(
                _(
                    "The activity has been read again from its source data. Your edits have been kept."
                ),
                category="success",
            )
        return redirect(url_for(".show", id=id))

    def _source_file_of(activity: Activity) -> pathlib.Path | None:
        """The file the user could have deleted along with the activity."""
        if not activity.path:
            return None
        path = pathlib.Path(activity.path)
        return path if path.is_file() else None

    @blueprint.route("/delete/<int:id>", methods=["GET"])
    @needs_authentication(authenticator)
    def confirm_delete(id: int) -> ResponseReturnValue:
        activity = DB.session.get(Activity, id)
        if activity is None:
            abort(404)
        return render_template(
            "activity/delete.html.j2",
            activity=activity,
            source_file=_source_file_of(activity),
        )

    @blueprint.route("/delete/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        activity = DB.session.get(Activity, id)
        if activity is None:
            abort(404)

        source_file = _source_file_of(activity)
        delete_source_file = (
            request.form.get("mode") == "delete_file" and source_file is not None
        )

        # The exclusion is recorded either way. It is what keeps an upstream export
        # from importing the activity again, and it is what an upload of the same
        # file clears when the user asks for the activity back.
        source = activity.source or ("directory" if activity.path else None)
        if source and activity.upstream_id:
            record_exclusion(
                source,
                str(activity.upstream_id),
                "deleted_by_user",
                path=activity.path,
            )
        activity.delete_data()
        DB.session.delete(activity)
        DB.session.commit()
        remove_activity_from_tile_state(id)

        if delete_source_file:
            assert source_file is not None
            source_file.unlink(missing_ok=True)
            flash(
                _("The activity and its source file %(path)s have been deleted.")
                % {"path": source_file},
                category="success",
            )
        else:
            flash(
                _(
                    "The activity has been hidden. Its source data is left untouched, but it will not be imported again. You can undo this from Settings → Excluded Activities, or by uploading the file again."
                ),
                category="success",
            )
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
    return to_vega(
        alt.Chart(time_series, title=_("Speed"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("speed", title=_("Speed / km/h")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
    )


def speed_distribution_plot(time_series: pd.DataFrame) -> str:
    df = pd.DataFrame(
        {
            "speed": time_series["speed"],
            "step": time_series["time"].diff().dt.total_seconds() / 60,
        }
    ).dropna()
    return to_vega(
        alt.Chart(df.loc[df["speed"] > 0], title=_("Speed distribution"))
        .mark_bar()
        .encode(
            alt.X("speed", bin=alt.Bin(step=5), title=_("Speed / km/h")),
            alt.Y("sum(step)", title=_("Duration / min")),
        )
    )


def distance_time_plot(time_series: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(time_series, title=_("Distance"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("distance_km", title=_("Distance / km")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive()
    )


def elevation_time_plot(time_series: pd.DataFrame) -> str:
    return to_vega(
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
    )


def elevation_gain_cum_plot(time_series: pd.DataFrame) -> str:
    return to_vega(
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
    )


def heart_rate_time_plot(time_series: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(time_series, title=_("Heart Rate"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("heartrate", scale=alt.Scale(zero=False), title=_("Heart rate")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
    )


def cadence_time_plot(time_series: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(time_series, title=_("Cadence"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("cadence", title=_("Cadence")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
    )


def power_time_plot(time_series: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(time_series, title=_("Power"))
        .mark_line()
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("power", scale=alt.Scale(zero=False), title=_("Power / W")),
            alt.Color("segment_id:N", title=_("Segment")),
        )
        .interactive(bind_y=False)
    )


def heart_rate_zone_plot(heart_zones: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(heart_zones, title=_("Heart Rate Zones"))
        .mark_bar()
        .encode(
            alt.X("minutes", title=_("Duration / min")),
            alt.Y("heartzone:O", title=_("Zone")),
            alt.Color("heartzone:O", scale=alt.Scale(scheme="turbo"), title=_("Zone")),
        )
    )


def name_tick_plot(meta: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(meta, title=_("Repetitions"))
        .mark_tick()
        .encode(
            alt.X("start_local", title=_("Date")),
        )
    )


def name_equipment_plot(meta: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(meta, title=_("Equipment"))
        .mark_bar()
        .encode(
            alt.X("count()", title=_("Count")), alt.Y("equipment", title=_("Equipment"))
        )
    )


def name_distance_plot(meta: pd.DataFrame) -> str:
    return to_vega(
        alt.Chart(meta, title=_("Distance"))
        .mark_bar()
        .encode(
            alt.X("distance_km", bin=True, title=_("Distance / km")),
            alt.Y("count()", title=_("Count")),
        )
    )


def name_minutes_plot(meta: pd.DataFrame) -> str:
    minutes = meta["elapsed_time"].dt.total_seconds() / 60
    return to_vega(
        alt.Chart(pd.DataFrame({"minutes": minutes}), title=_("Elapsed time"))
        .mark_bar()
        .encode(
            alt.X("minutes", bin=True, title=_("Time / min")),
            alt.Y("count()", title=_("Count")),
        )
    )


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
