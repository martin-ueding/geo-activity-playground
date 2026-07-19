import geojson
import sqlalchemy
from flask import Blueprint, Response, redirect, render_template, request, url_for

from ...core.datamodel import DB
from ...core.tiles import get_tile_upper_left_lat_lon
from ...explorer.grid_file import (
    make_explorer_rectangle,
    make_grid_file_geojson,
    make_grid_file_gpx,
    make_grid_points,
)
from ...explorer.tile_visits import (
    get_explorer_square,
    get_tile_medians,
    get_tile_visits_in_bounds,
)
from .model import SquarePlannerBookmark


def make_square_planner_blueprint() -> Blueprint:
    blueprint = Blueprint("square_planner", __name__, template_folder="templates")

    @blueprint.route("/<int:zoom>")
    def landing(zoom: int):
        square_x, square_y, square_size = get_explorer_square(zoom)
        if square_x is None or square_y is None or square_size <= 0:
            square_x, square_y = get_tile_medians(zoom)
            square_size = 1
        return redirect(
            url_for(
                "square_planner.index",
                zoom=zoom,
                x=square_x,
                y=square_y,
                size=square_size,
            )
        )

    @blueprint.route("/<int:zoom>/<int:x>/<int:y>/<int:size>")
    def index(zoom: int, x: int, y: int, size: int):
        square_geojson = geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_rectangle(
                        x,
                        y,
                        x + size,
                        y + size,
                        zoom,
                    )
                ]
            )
        )

        medians = get_tile_medians(zoom)
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians[0], medians[1], zoom
        )

        return render_template(
            "square_planner/index.html.j2",
            square_geojson=square_geojson,
            zoom=zoom,
            square_x=x,
            square_y=y,
            square_size=size,
            bookmarks=DB.session.scalars(
                sqlalchemy.select(SquarePlannerBookmark)
            ).all(),
            center={
                "latitude": median_lat,
                "longitude": median_lon,
            },
        )

    @blueprint.route("/<int:zoom>/<int:x>/<int:y>/<int:size>/missing.<suffix>")
    def square_planner_missing(zoom: int, x: int, y: int, size: int, suffix: str):
        tile_visits = get_tile_visits_in_bounds(zoom, x, x + size - 1, y, y + size - 1)
        points = make_grid_points(
            (
                (tile_x, tile_y)
                for tile_x in range(x, x + size)
                for tile_y in range(y, y + size)
                if (tile_x, tile_y) not in tile_visits
            ),
            zoom,
        )
        if suffix == "geojson":
            response = make_grid_file_geojson(points)
        elif suffix == "gpx":
            response = make_grid_file_gpx(points)
        else:
            raise RuntimeError(f"Unsupported suffix {suffix}.")

        mimetypes = {"geojson": "application/json", "gpx": "application/xml"}
        return Response(
            response,
            mimetype=mimetypes[suffix],
            headers={"Content-disposition": "attachment"},
        )

    @blueprint.route(
        "/save-bookmark/<int:zoom>/<int:x>/<int:y>/<int:size>", methods=["POST"]
    )
    def save_bookmark(zoom: int, x: int, y: int, size: int):
        bookmark = SquarePlannerBookmark(
            zoom=zoom, x=x, y=y, size=size, name=request.form["name"]
        )
        DB.session.add(bookmark)
        DB.session.commit()
        return redirect(request.referrer)

    @blueprint.route("/delete-bookmark/<int:id>")
    def delete_bookmark(id: int):
        bookmark = DB.session.get(SquarePlannerBookmark, id)
        DB.session.delete(bookmark)
        DB.session.commit()
        return redirect(request.referrer)

    return blueprint
