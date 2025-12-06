import altair as alt
import geojson
import numpy as np
import pandas as pd
import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.config import Config
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.datamodel import Segment
from ...core.segments import extract_segment_from_geojson
from ...core.segments import find_matches
from ...core.segments import segment_track_distance
from ...explorer.tile_visits import TileVisitAccessor
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes


def make_segments_blueprint(
    authenticator: Authenticator,
    tile_visit_accessor: TileVisitAccessor,
    flasher: Flasher,
    config: Config,
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

            find_matches(
                segment,
                tile_visit_accessor.tile_state["activities_per_tile"][17],
                config,
            )
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
        return render_template(
            "segments/show.html.j2",
            segment=segment,
            activity_ids=[match.activity_id for match in segment.matches],
            plots=make_plots(df),
            table=df.to_dict("records"),
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

    @blueprint.route("/match-info/<int:activity_id>/<int:segment_id>")
    def match_info(activity_id: int, segment_id: int) -> ResponseReturnValue:
        activity = DB.session.get_one(Activity, activity_id)
        segment = DB.session.get_one(Segment, segment_id)
        distance_m, index, distance_matrix = segment_track_distance(
            segment, activity, config
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


def segment_df(segment: Segment) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "distance_km": abs(match.distance_km),
            "duration_s": abs(match.duration.total_seconds()),
            "duration": abs(match.duration),
            "direction": (
                "Forward" if match.duration.total_seconds() > 0 else "Backward"
            ),
            "entry_time": match.entry_time,
            "exit_time": match.exit_time,
            "activity_id": match.activity.id,
            "activity_name": match.activity.name,
            "equipment_name": (
                match.activity.equipment.name
                if match.activity.equipment is not None
                else ""
            ),
            "kind_name": (
                match.activity.kind.name if match.activity.kind is not None else ""
            ),
        }
        for match in segment.matches
    ).sort_values("entry_time", ascending=False)


def make_plots(df: pd.DataFrame) -> dict[str, str]:
    duration_histogram = (
        alt.Chart(df, width=500)
        .mark_bar()
        .encode(
            alt.X("duration_s", bin=alt.Bin(step=15), title=_("Duration / s")),
            alt.Y("count()"),
            alt.Color("direction", title=_("Direction")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )

    duration_boxplot = (
        alt.Chart(df, width=500)
        .mark_boxplot()
        .encode(
            alt.Y("direction", title=_("Direction")),
            alt.X("duration_s", title=_("Duration / s")),
            alt.Color("direction", title=_("Direction")),
        )
        .to_json(format="vega")
    )

    return {
        _("Duration Histogram"): duration_histogram,
        _("Duration by Direction"): duration_boxplot,
    }
