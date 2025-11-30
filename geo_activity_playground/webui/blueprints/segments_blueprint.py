import geojson
import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask.typing import ResponseReturnValue

from ...core.datamodel import DB
from ...core.datamodel import Segment
from ...core.segments import extract_segment_from_geojson
from ...core.segments import find_matches
from ...explorer.tile_visits import TileVisitAccessor
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes


def make_segments_blueprint(
    authenticator: Authenticator,
    tile_visit_accessor: TileVisitAccessor,
    flasher: Flasher,
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
        pass

    return blueprint
