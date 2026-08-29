import geojson
import sqlalchemy as sa
from flask import Blueprint, jsonify, render_template, request

from ...core.datamodel import DB
from ...core.tile_visits import get_tile_medians
from ...core.tiles import get_tile_upper_left_lat_lon
from .model import StreetChunk, StreetChunkVisit

MAX_CHUNKS_PER_REQUEST = 20_000


def make_streets_blueprint() -> Blueprint:
    blueprint = Blueprint("streets", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        zoom = 14
        medians = get_tile_medians(zoom)
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians[0], medians[1], zoom
        )
        return render_template(
            "streets/index.html.j2",
            center={"latitude": median_lat, "longitude": median_lon},
        )

    @blueprint.route("/geojson")
    def chunks_geojson():
        south = float(request.args["south"])
        west = float(request.args["west"])
        north = float(request.args["north"])
        east = float(request.args["east"])

        rows = (
            sa.select(
                StreetChunk.lat1,
                StreetChunk.lon1,
                StreetChunk.lat2,
                StreetChunk.lon2,
                StreetChunkVisit.id.is_not(None).label("visited"),
            )
            .select_from(StreetChunk)
            .outerjoin(StreetChunkVisit, StreetChunkVisit.chunk_id == StreetChunk.id)
            .where(
                sa.or_(
                    sa.and_(
                        StreetChunk.lat1.between(south, north),
                        StreetChunk.lon1.between(west, east),
                    ),
                    sa.and_(
                        StreetChunk.lat2.between(south, north),
                        StreetChunk.lon2.between(west, east),
                    ),
                )
            )
            .limit(MAX_CHUNKS_PER_REQUEST)
        )

        features = [
            geojson.Feature(
                geometry=geojson.LineString([(lon1, lat1), (lon2, lat2)]),
                properties={"visited": bool(visited)},
            )
            for lat1, lon1, lat2, lon2, visited in DB.session.execute(rows)
        ]
        return jsonify(geojson.FeatureCollection(features))

    return blueprint
