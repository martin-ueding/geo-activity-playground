import datetime
import io
import itertools
import logging

import altair as alt
import geojson
import matplotlib
import matplotlib.pyplot as pl
import numpy as np
import pandas as pd
import sqlalchemy
from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import Response
from flask import url_for

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.coordinates import Bounds
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.raster_map import ImageTransform
from ...core.raster_map import TileGetter
from ...core.tiles import compute_tile
from ...core.tiles import get_tile_upper_left_lat_lon
from ...explorer.grid_file import get_border_tiles
from ...explorer.grid_file import make_explorer_rectangle
from ...explorer.grid_file import make_explorer_tile
from ...explorer.grid_file import make_grid_file_geojson
from ...explorer.grid_file import make_grid_file_gpx
from ...explorer.grid_file import make_grid_points
from ...explorer.tile_visits import compute_tile_evolution
from ...explorer.tile_visits import TileEvolutionState
from ...explorer.tile_visits import TileVisitAccessor
from ..authenticator import Authenticator
from ..authenticator import needs_authentication

alt.data_transformers.enable("vegafusion")

logger = logging.getLogger(__name__)


def make_explorer_blueprint(
    authenticator: Authenticator,
    tile_visit_accessor: TileVisitAccessor,
    config_accessor: ConfigAccessor,
    tile_getter: TileGetter,
    image_transforms: dict[str, ImageTransform],
) -> Blueprint:
    blueprint = Blueprint("explorer", __name__, template_folder="templates")

    @blueprint.route("/<int:zoom>")
    def map(zoom: int):
        if zoom not in config_accessor().explorer_zoom_levels:
            return {"zoom_level_not_generated": zoom}

        tile_evolution_states = tile_visit_accessor.tile_state["evolution_state"]
        tile_visits = tile_visit_accessor.tile_state["tile_visits"]
        tile_histories = tile_visit_accessor.tile_state["tile_history"]

        medians = tile_histories[zoom].median()
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )

        explored = get_three_color_tiles(
            tile_visits[zoom], tile_evolution_states[zoom], zoom
        )

        context = {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": (
                    bounding_box_for_biggest_cluster(
                        tile_evolution_states[zoom].clusters.values(), zoom
                    )
                    if len(tile_evolution_states[zoom].memberships) > 0
                    else {}
                ),
            },
            "explored": explored,
            "plot_tile_evolution": plot_tile_evolution(tile_histories[zoom]),
            "plot_cluster_evolution": plot_cluster_evolution(
                tile_evolution_states[zoom].cluster_evolution
            ),
            "plot_square_evolution": plot_square_evolution(
                tile_evolution_states[zoom].square_evolution
            ),
            "zoom": zoom,
        }
        return render_template("explorer/index.html.j2", **context)

    @blueprint.route("/enable-zoom-level/<int:zoom>")
    @needs_authentication(authenticator)
    def enable_zoom_level(zoom: int):
        if 0 <= zoom <= 19:
            config_accessor().explorer_zoom_levels.append(zoom)
            config_accessor().explorer_zoom_levels.sort()
            config_accessor.save()
            compute_tile_evolution(tile_visit_accessor, config_accessor())
            flash(f"Enabled {zoom=} for explorer tiles.", category="success")
        else:
            flash(f"{zoom=} is not valid, must be between 0 and 19.", category="danger")
        return redirect(url_for(".map", zoom=zoom))

    @blueprint.route(
        "/<int:zoom>/<float:north>/<float:east>/<float:south>/<float:west>/explored.<suffix>"
    )
    def download(
        zoom: int, north: float, east: float, south: float, west: float, suffix: str
    ):
        x1, y1 = compute_tile(north, west, zoom)
        x2, y2 = compute_tile(south, east, zoom)
        tile_bounds = Bounds(x1, y1, x2 + 2, y2 + 2)

        tile_histories = tile_visit_accessor.tile_state["tile_history"]
        tiles = tile_histories[zoom]
        points = get_border_tiles(tiles, zoom, tile_bounds)
        if suffix == "geojson":
            result = make_grid_file_geojson(points)
        elif suffix == "gpx":
            result = make_grid_file_gpx(points)

        mimetypes = {"geojson": "application/json", "gpx": "application/xml"}
        return Response(
            result,
            mimetype=mimetypes[suffix],
            headers={"Content-disposition": "attachment"},
        )

    @blueprint.route(
        "/<int:zoom>/<float:north>/<float:east>/<float:south>/<float:west>/missing.<suffix>"
    )
    def missing(
        zoom: int, north: float, east: float, south: float, west: float, suffix: str
    ):
        x1, y1 = compute_tile(north, west, zoom)
        x2, y2 = compute_tile(south, east, zoom)
        tile_bounds = Bounds(x1, y1, x2 + 2, y2 + 2)

        tile_visits = tile_visit_accessor.tile_state["tile_visits"]
        tiles = tile_visits[zoom]
        points = make_grid_points(
            (tile for tile in tiles.keys() if tile_bounds.contains(*tile)), zoom
        )
        if suffix == "geojson":
            result = make_grid_file_geojson(points)
        elif suffix == "gpx":
            result = make_grid_file_gpx(points)

        mimetypes = {"geojson": "application/json", "gpx": "application/xml"}
        return Response(
            result,
            mimetype=mimetypes[suffix],
            headers={"Content-disposition": "attachment"},
        )

    @blueprint.route("/<int:zoom>/server-side")
    def server_side(zoom: int):
        if zoom not in config_accessor().explorer_zoom_levels:
            return {"zoom_level_not_generated": zoom}

        tile_evolution_states = tile_visit_accessor.tile_state["evolution_state"]
        tile_histories = tile_visit_accessor.tile_state["tile_history"]

        medians = tile_histories[zoom].median()
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )

        context = {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": (
                    bounding_box_for_biggest_cluster(
                        tile_evolution_states[zoom].clusters.values(), zoom
                    )
                    if len(tile_evolution_states[zoom].memberships) > 0
                    else {}
                ),
            },
            "plot_tile_evolution": plot_tile_evolution(tile_histories[zoom]),
            "plot_cluster_evolution": plot_cluster_evolution(
                tile_evolution_states[zoom].cluster_evolution
            ),
            "plot_square_evolution": plot_square_evolution(
                tile_evolution_states[zoom].square_evolution
            ),
            "zoom": zoom,
        }
        return render_template("explorer/server-side.html.j2", **context)

    @blueprint.route("/<int:zoom>/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(zoom: int, z: int, x: int, y: int) -> Response:
        tile_visits = tile_visit_accessor.tile_state["tile_visits"][zoom]

        map_tile = np.array(tile_getter.get_tile(z, x, y)) / 255
        if z >= zoom:
            factor = 2 ** (z - zoom)
            if (x // factor, y // factor) in tile_visits:
                map_tile = image_transforms["color"].transform_image(map_tile)
            else:
                map_tile = image_transforms["color"].transform_image(map_tile) / 1.2
        else:
            grayscale = image_transforms["color"].transform_image(map_tile) / 1.2
            factor = 2 ** (zoom - z)
            width = 256 // factor
            for xo in range(factor):
                for yo in range(factor):
                    if (x * factor + xo, y * factor + yo) not in tile_visits:
                        map_tile[
                            yo * width : (yo + 1) * width, xo * width : (xo + 1) * width
                        ] = grayscale[
                            yo * width : (yo + 1) * width, xo * width : (xo + 1) * width
                        ]
        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")

    return blueprint


def get_three_color_tiles(
    tile_visits: dict,
    cluster_state: TileEvolutionState,
    zoom: int,
) -> str:
    logger.info("Generate data for explorer tile map …")
    today = datetime.date.today()
    cmap_first = matplotlib.colormaps["plasma"]
    cmap_last = matplotlib.colormaps["plasma"]
    tile_dict = {}
    for tile, tile_data in tile_visits.items():
        if not pd.isna(tile_data["first_time"]):
            first_age_days = (today - tile_data["first_time"].date()).days
            last_age_days = (today - tile_data["last_time"].date()).days
        else:
            first_age_days = 10000
            last_age_days = 10000
        tile_dict[tile] = {
            "first_activity_id": str(tile_data["first_id"]),
            "first_activity_name": DB.session.scalar(
                sqlalchemy.select(Activity.name).where(
                    Activity.id == tile_data["first_id"]
                )
            ),
            "last_activity_id": str(tile_data["last_id"]),
            "last_activity_name": DB.session.scalar(
                sqlalchemy.select(Activity.name).where(
                    Activity.id == tile_data["last_id"]
                )
            ),
            "first_age_days": first_age_days,
            "first_age_color": matplotlib.colors.to_hex(
                cmap_first(max(1 - first_age_days / (2 * 365), 0.0))
            ),
            "last_age_days": last_age_days,
            "last_age_color": matplotlib.colors.to_hex(
                cmap_last(max(1 - last_age_days / (2 * 365), 0.0))
            ),
            "cluster": False,
            "color": "#303030",
            "first_visit": tile_data["first_time"].date().isoformat(),
            "last_visit": tile_data["last_time"].date().isoformat(),
            "num_visits": len(tile_data["activity_ids"]),
            "square": False,
            "tile": f"({zoom}, {tile[0]}, {tile[1]})",
        }

    # Mark biggest square.
    if cluster_state.max_square_size:
        for x in range(
            cluster_state.square_x,
            cluster_state.square_x + cluster_state.max_square_size,
        ):
            for y in range(
                cluster_state.square_y,
                cluster_state.square_y + cluster_state.max_square_size,
            ):
                tile_dict[(x, y)]["square"] = True

    # Add cluster information.
    for members in cluster_state.clusters.values():
        for member in members:
            tile_dict[member]["this_cluster_size"] = len(members)
            tile_dict[member]["cluster"] = True
    if len(cluster_state.cluster_evolution) > 0:
        max_cluster_size = cluster_state.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_size = 0
    num_cluster_tiles = len(cluster_state.memberships)

    # Apply cluster colors.
    cluster_cmap = matplotlib.colormaps["tab10"]
    for color, members in zip(
        itertools.cycle(map(cluster_cmap, [0, 1, 2, 3, 4, 5, 6, 8, 9])),
        sorted(
            cluster_state.clusters.values(),
            key=lambda members: len(members),
            reverse=True,
        ),
    ):
        hex_color = matplotlib.colors.to_hex(color)
        for member in members:
            tile_dict[member]["color"] = hex_color

    if cluster_state.max_square_size:
        square_geojson = geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_rectangle(
                        cluster_state.square_x,
                        cluster_state.square_y,
                        cluster_state.square_x + cluster_state.max_square_size,
                        cluster_state.square_y + cluster_state.max_square_size,
                        zoom,
                    )
                ]
            )
        )
    else:
        square_geojson = "{}"

    try:
        feature_collection = geojson.FeatureCollection(
            features=[
                make_explorer_tile(x, y, v, zoom) for (x, y), v in tile_dict.items()
            ]
        )
        explored_geojson = geojson.dumps(feature_collection)
    except TypeError as e:
        logger.error(f"Encountered TypeError while building GeoJSON: {e=}")
        logger.error(f"{tile_dict = }")
        raise

    result = {
        "explored_geojson": explored_geojson,
        "max_cluster_size": max_cluster_size,
        "num_cluster_tiles": num_cluster_tiles,
        "num_tiles": len(tile_dict),
        "square_size": cluster_state.max_square_size,
        "square_x": cluster_state.square_x,
        "square_y": cluster_state.square_y,
        "square_geojson": square_geojson,
    }
    return result


def bounding_box_for_biggest_cluster(
    clusters: list[list[tuple[int, int]]], zoom: int
) -> str:
    biggest_cluster = max(clusters, key=lambda members: len(members))
    min_x = min(x for x, y in biggest_cluster)
    max_x = max(x for x, y in biggest_cluster)
    min_y = min(y for x, y in biggest_cluster)
    max_y = max(y for x, y in biggest_cluster)
    lat_max, lon_min = get_tile_upper_left_lat_lon(min_x, min_y, zoom)
    lat_min, lon_max = get_tile_upper_left_lat_lon(max_x, max_y, zoom)
    return geojson.dumps(
        geojson.Feature(
            geometry=geojson.Polygon(
                [
                    [
                        (lon_min, lat_max),
                        (lon_max, lat_max),
                        (lon_max, lat_min),
                        (lon_min, lat_min),
                        (lon_min, lat_max),
                    ]
                ]
            ),
        )
    )


def plot_tile_evolution(tiles: pd.DataFrame) -> str:
    if len(tiles) == 0:
        return ""
    tiles["count"] = np.arange(1, len(tiles) + 1)
    return (
        alt.Chart(tiles, title="Tiles")
        .mark_line(interpolate="step-after")
        .encode(alt.X("time", title="Time"), alt.Y("count", title="Number of tiles"))
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def plot_cluster_evolution(cluster_evolution: pd.DataFrame) -> str:
    if len(cluster_evolution) == 0:
        return ""
    return (
        alt.Chart(cluster_evolution, title="Cluster")
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title="Time"),
            alt.Y("max_cluster_size", title="Maximum cluster size"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def plot_square_evolution(square_evolution: pd.DataFrame) -> str:
    if len(square_evolution) == 0:
        return ""
    return (
        alt.Chart(square_evolution, title="Square")
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title="Time"),
            alt.Y("max_square_size", title="Maximum square size"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )
