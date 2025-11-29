"""Blueprint for segment management (CRUD operations)."""

import json
import logging

import geojson
from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask.typing import ResponseReturnValue

from ...core.datamodel import DB
from ...core.datamodel import Segment
from ...core.datamodel import SegmentMatch
from ...core.segments import match_new_segment_to_activities
from ...explorer.tile_visits import TileVisitAccessor
from ..authenticator import Authenticator
from ..authenticator import needs_authentication

logger = logging.getLogger(__name__)


def _segments_to_geojson(segments: list[Segment]) -> str:
    """Convert segments to GeoJSON FeatureCollection."""
    features = []
    colors = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628", "#f781bf", "#999999"]
    
    for i, segment in enumerate(segments):
        coords = segment.coordinates
        feature = geojson.Feature(
            geometry=geojson.LineString(coordinates=coords),
            properties={
                "segment_id": segment.id,
                "segment_name": segment.name,
                "color": colors[i % len(colors)],
                "length_km": round(segment.length_km, 2),
                "match_count": len(segment.matches),
            },
        )
        features.append(feature)
    
    return geojson.dumps(geojson.FeatureCollection(features))


def make_segment_blueprint(
    authenticator: Authenticator,
    tile_visit_accessor: TileVisitAccessor,
) -> Blueprint:
    blueprint = Blueprint("segment", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        """List all segments with map."""
        segments = DB.session.query(Segment).order_by(Segment.name).all()
        segments_geojson = _segments_to_geojson(segments) if segments else None
        return render_template(
            "segment/index.html.j2", 
            segments=segments, 
            segments_geojson=segments_geojson
        )

    @blueprint.route("/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def new() -> ResponseReturnValue:
        """Create a new segment from uploaded GeoJSON file."""
        if request.method == "POST":
            name = request.form.get("name", "").strip()

            if not name:
                flash("Please provide a name for the segment.", category="danger")
                return render_template("segment/new.html.j2")

            # Handle file upload
            if "geojson_file" not in request.files:
                flash("Please upload a GeoJSON file.", category="danger")
                return render_template("segment/new.html.j2")

            file = request.files["geojson_file"]
            if file.filename == "":
                flash("No file selected.", category="danger")
                return render_template("segment/new.html.j2")

            # Read and parse GeoJSON
            try:
                geojson_str = file.read().decode("utf-8")
                geojson_data = json.loads(geojson_str)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                flash(f"Invalid GeoJSON file: {e}", category="danger")
                return render_template("segment/new.html.j2")

            # Extract coordinates from GeoJSON
            coordinates = _extract_linestring_coordinates(geojson_data)
            if coordinates is None:
                flash(
                    "Could not find a LineString geometry in the GeoJSON file. "
                    "Make sure you export as GeoJSON from bikerouter.de.",
                    category="danger",
                )
                return render_template("segment/new.html.j2")

            if len(coordinates) < 2:
                flash(
                    "The segment must have at least 2 points.",
                    category="danger",
                )
                return render_template("segment/new.html.j2")

            # Create segment
            segment = Segment(name=name)
            segment.coordinates = coordinates
            DB.session.add(segment)
            DB.session.commit()

            # Match to existing activities
            activities_per_tile = tile_visit_accessor.tile_state["activities_per_tile"][18]
            num_matches = match_new_segment_to_activities(
                segment, activities_per_tile
            )

            flash(
                f"Created segment '{name}' with {len(coordinates)} points. "
                f"Found {num_matches} matching activities.",
                category="success",
            )
            return redirect(url_for(".index"))

        return render_template("segment/new.html.j2")

    @blueprint.route("/<int:id>")
    def show(id: int) -> ResponseReturnValue:
        """Show segment details with all matching activities."""
        segment = DB.session.get(Segment, id)
        if segment is None:
            flash("Segment not found.", category="danger")
            return redirect(url_for(".index"))

        # Get matches sorted by duration (fastest first), then by date
        matches = (
            DB.session.query(SegmentMatch)
            .filter(SegmentMatch.segment_id == id)
            .order_by(SegmentMatch.duration.asc().nullslast())
            .all()
        )

        # Generate GeoJSON for this segment
        segment_geojson = geojson.dumps(
            geojson.Feature(
                geometry=geojson.LineString(coordinates=segment.coordinates),
                properties={"name": segment.name},
            )
        )

        return render_template(
            "segment/show.html.j2",
            segment=segment,
            matches=matches,
            segment_geojson=segment_geojson,
        )

    @blueprint.route("/delete/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        """Delete a segment and all its matches."""
        segment = DB.session.get(Segment, id)
        if segment is None:
            flash("Segment not found.", category="danger")
            return redirect(url_for(".index"))

        name = segment.name
        DB.session.delete(segment)
        DB.session.commit()

        flash(f"Deleted segment '{name}'.", category="success")
        return redirect(url_for(".index"))

    return blueprint


def _extract_linestring_coordinates(geojson: dict) -> list[list[float]] | None:
    """Extract LineString coordinates from various GeoJSON formats.

    Supports:
    - Direct LineString geometry
    - Feature with LineString geometry
    - FeatureCollection with a single LineString feature

    Returns:
        List of [lon, lat] coordinate pairs, or None if not found.
    """
    geometry = None

    if geojson.get("type") == "LineString":
        geometry = geojson
    elif geojson.get("type") == "Feature":
        geometry = geojson.get("geometry")
    elif geojson.get("type") == "FeatureCollection":
        features = geojson.get("features", [])
        for feature in features:
            geom = feature.get("geometry", {})
            if geom.get("type") == "LineString":
                geometry = geom
                break

    if geometry is None or geometry.get("type") != "LineString":
        return None

    return geometry.get("coordinates", [])

