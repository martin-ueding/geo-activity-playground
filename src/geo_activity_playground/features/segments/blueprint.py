import altair as alt
import geojson
import numpy as np
import pandas as pd
import sqlalchemy
from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Activity
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from .analysis import make_plots, segment_df
from .matching import (
    extract_segment_from_geojson,
    find_matches,
    rematch_segment,
    segment_track_distance,
)
from .model import Segment


def make_segments_blueprint(
    authenticator: Authenticator,
    flasher: Flasher,
    config_accessor: ConfigAccessor,
) -> Blueprint:
    blueprint = Blueprint("segments", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        return render_template(
            "segments/index.html.j2",
            segments=DB.session.scalars(sqlalchemy.select(Segment)).all(),
        )

    @blueprint.route("/new", methods=["POST"])
    @needs_authentication(authenticator)
    def new() -> ResponseReturnValue:
        if request.method == "POST":
            if "file" not in request.files:
                flasher.flash_message(
                    "No file could be found. Did you select a file?", FlashTypes.WARNING
                )
                return redirect(url_for(".index"))

            file = request.files["file"]
            geojson_str = file.read().decode()
            segment_coords = extract_segment_from_geojson(geojson_str)
            name = request.form["name"]

            segment = Segment(name=name)
            segment.coordinates = segment_coords
            DB.session.add(segment)
            DB.session.commit()

            flasher.flash_message(f"Created segment “{name}”.", FlashTypes.SUCCESS)

            find_matches(segment, config_accessor.activity_import())
        return redirect(url_for(".index"))

    @blueprint.route("/line/<int:id>/line.geojson")
    def line(id: int) -> ResponseReturnValue:
        segment = DB.session.get_one(Segment, id)
        gj = geojson.Feature(
            geometry=geojson.LineString(
                coordinates=[[lon, lat] for lat, lon in segment.coordinates]
            )
        )
        return geojson.dumps(gj)

    @blueprint.route("/show/<int:id>")
    def show(id: int) -> ResponseReturnValue:
        segment = DB.session.get_one(Segment, id)
        df = segment_df(segment)
        visible = {
            name: name in config_accessor.ui().visible_table_columns
            for name in (
                "distance",
                "duration",
                "direction",
                "average_speed",
                "average_power",
                "equipment",
                "kind",
            )
        }
        return render_template(
            "segments/show.html.j2",
            segment=segment,
            activity_ids=[match.activity_id for match in segment.matches],
            plots=make_plots(df),
            table=df.to_dict("records"),
            visible=visible,
        )

    @blueprint.route("/delete/<int:id>")
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        segment = DB.session.get_one(Segment, id)
        name = segment.name
        DB.session.delete(segment)
        DB.session.commit()
        flasher.flash_message(f"Deleted segment “{name}”.", FlashTypes.SUCCESS)
        return redirect(url_for(".index"))

    @blueprint.route("/rematch/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def rematch(id: int) -> ResponseReturnValue:
        segment = DB.session.get_one(Segment, id)
        deleted_matches, _ = rematch_segment(segment, config_accessor.activity_import())
        flasher.flash_message(
            f"Re-matched segment “{segment.name}” after deleting {deleted_matches} previous matches.",
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".show", id=segment.id))

    @blueprint.route("/match-info/<int:activity_id>/<int:segment_id>")
    def match_info(activity_id: int, segment_id: int) -> ResponseReturnValue:
        activity = DB.session.get_one(Activity, activity_id)
        segment = DB.session.get_one(Segment, segment_id)
        distance_m, index, distance_matrix = segment_track_distance(
            segment, activity, config_accessor.activity_import()
        )
        np.save(f"distance-{activity.id}-{segment.id}.npy", distance_matrix)

        segment_index, track_index = np.meshgrid(*map(np.arange, distance_matrix.shape))

        distance_df = pd.DataFrame(
            {
                "distance_m": distance_matrix.ravel(),
                "segment_index": segment_index.ravel(),
                "track_index": track_index.ravel(),
            }
        )

        distance_chart = (
            alt.Chart(distance_df)
            .mark_rect()
            .encode(
                alt.X("track_index", title=_("Track Index")),
                alt.Y("segment_index", title=_("Segment Index")),
                alt.Color(
                    "distance_m",
                    scale=alt.Scale(scheme="viridis"),
                    title=_("Distance / m"),
                ),
            )
            .to_json(format="vega")
        )

        return render_template(
            "segments/match-info.html.j2",
            activity=activity,
            segment=segment,
            distance_chart=distance_chart,
        )

    return blueprint
