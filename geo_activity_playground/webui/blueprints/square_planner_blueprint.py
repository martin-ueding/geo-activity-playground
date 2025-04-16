import geojson
import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for

from ...core.datamodel import DB
from ...core.datamodel import SquarePlannerBookmark
from ...explorer.grid_file import make_explorer_rectangle
from ...explorer.grid_file import make_explorer_tile
from ...explorer.grid_file import make_grid_file_geojson
from ...explorer.grid_file import make_grid_file_gpx
from ...explorer.grid_file import make_grid_points
from ...explorer.tile_visits import TileVisitAccessor


def make_square_planner_blueprint(tile_visit_accessor: TileVisitAccessor) -> Blueprint:
    tile_visits = tile_visit_accessor.tile_state["tile_visits"]

    blueprint = Blueprint("square_planner", __name__, template_folder="templates")

    @blueprint.route("/<int:zoom>")
    def landing(zoom: int):
        explored = tile_visit_accessor.tile_state["evolution_state"][zoom]
        return redirect(
            url_for(
                "square_planner.index",
                zoom=zoom,
                x=explored.square_x,
                y=explored.square_y,
                size=explored.max_square_size,
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

        missing_geojson = geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_tile(
                        tile_x,
                        tile_y,
                        {},
                        zoom,
                    )
                    for tile_x in range(x, x + size)
                    for tile_y in range(y, y + size)
                    if (tile_x, tile_y) not in set(tile_visits[zoom].keys())
                ]
            )
        )

        return render_template(
            "square_planner/index.html.j2",
            explored_geojson=_get_explored_geojson(tile_visits[zoom].keys(), zoom),
            missing_geojson=missing_geojson,
            square_geojson=square_geojson,
            zoom=zoom,
            square_x=x,
            square_y=y,
            square_size=size,
            bookmarks=DB.session.scalars(
                sqlalchemy.select(SquarePlannerBookmark)
            ).all(),
        )

    @blueprint.route("/<int:zoom>/<int:x>/<int:y>/<int:size>/missing.<suffix>")
    def square_planner_missing(zoom: int, x: int, y: int, size: int, suffix: str):
        points = make_grid_points(
            (
                (tile_x, tile_y)
                for tile_x in range(x, x + size)
                for tile_y in range(y, y + size)
                if (tile_x, tile_y) not in set(tile_visits[zoom].keys())
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


def _get_explored_geojson(tile_visits: list[tuple[int, int]], zoom: int) -> str:
    return geojson.dumps(
        geojson.FeatureCollection(
            features=[
                make_explorer_tile(
                    tile_x,
                    tile_y,
                    {},
                    zoom,
                )
                for tile_x, tile_y in tile_visits
            ]
        )
    )
