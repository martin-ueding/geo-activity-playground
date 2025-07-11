import io
import logging
import pathlib

import matplotlib.pylab as pl
import numpy as np
from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response
from PIL import Image
from PIL import ImageDraw

from ...core.activities import ActivityRepository
from ...core.config import Config
from ...core.meta_search import apply_search_query
from ...core.meta_search import SearchQuery
from ...core.raster_map import convert_to_grayscale
from ...core.raster_map import GeoBounds
from ...core.raster_map import get_sensible_zoom_level
from ...core.raster_map import get_tile
from ...core.raster_map import OSM_TILE_SIZE
from ...core.raster_map import PixelBounds
from ...core.tasks import work_tracker
from ...core.tiles import get_tile_upper_left_lat_lon
from ...explorer.tile_visits import TileVisitAccessor
from ..search_util import search_query_from_form
from ..search_util import SearchQueryHistory
from .explorer_blueprint import bounding_box_for_biggest_cluster

logger = logging.getLogger(__name__)


def make_heatmap_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    search_query_history: SearchQueryHistory,
) -> Blueprint:
    blueprint = Blueprint("heatmap", __name__, template_folder="templates")

    tile_histories = tile_visit_accessor.tile_state["tile_history"]
    tile_evolution_states = tile_visit_accessor.tile_state["evolution_state"]
    tile_visits = tile_visit_accessor.tile_state["tile_visits"]
    activities_per_tile = tile_visit_accessor.tile_state["activities_per_tile"]

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)

        zoom = 14
        tiles = tile_histories[zoom]
        medians = tiles[["tile_x", "tile_y"]].median(skipna=True)
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians["tile_x"], medians["tile_y"], zoom
        )
        cluster_state = tile_evolution_states[zoom]

        context = {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": (
                    bounding_box_for_biggest_cluster(
                        cluster_state.clusters.values(), zoom
                    )
                    if len(cluster_state.memberships) > 0
                    else {}
                ),
            },
            "extra_args": query.to_url_str(),
            "query": query.to_jinja(),
        }

        return render_template("heatmap/index.html.j2", **context)

    @blueprint.route("/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(x: int, y: int, z: int):
        query = search_query_from_form(request.args)
        f = io.BytesIO()
        pl.imsave(
            f,
            _render_tile_image(x, y, z, query, config, repository, activities_per_tile),
            format="png",
        )
        return Response(
            bytes(f.getbuffer()),
            mimetype="image/png",
        )

    @blueprint.route(
        "/download/<float:north>/<float:east>/<float:south>/<float:west>/heatmap.png"
    )
    def download(north: float, east: float, south: float, west: float):
        query = search_query_from_form(request.args)
        geo_bounds = GeoBounds(south, west, north, east)
        tile_bounds = get_sensible_zoom_level(geo_bounds, (4000, 4000))
        pixel_bounds = PixelBounds.from_tile_bounds(tile_bounds)

        background = np.zeros((*pixel_bounds.shape, 3))
        for x in range(tile_bounds.x1, tile_bounds.x2):
            for y in range(tile_bounds.y1, tile_bounds.y2):
                i = y - tile_bounds.y1
                j = x - tile_bounds.x1

                background[
                    i * OSM_TILE_SIZE : (i + 1) * OSM_TILE_SIZE,
                    j * OSM_TILE_SIZE : (j + 1) * OSM_TILE_SIZE,
                    :,
                ] = _render_tile_image(
                    x,
                    y,
                    tile_bounds.zoom,
                    query,
                    config,
                    repository,
                    activities_per_tile,
                )

        f = io.BytesIO()
        pl.imsave(f, background, format="png")
        return Response(
            bytes(f.getbuffer()),
            mimetype="image/png",
            headers={"Content-disposition": 'attachment; filename="heatmap.png"'},
        )

    return blueprint


def _get_counts(
    x: int,
    y: int,
    z: int,
    query: SearchQuery,
    repository: ActivityRepository,
    activities_per_tile: dict[int, dict[tuple[int, int], set[int]]],
) -> np.ndarray:
    tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
    tile_counts = np.zeros(tile_pixels, dtype=np.int32)
    if not query.active:
        tile_count_cache_path = pathlib.Path(f"Cache/Heatmap/{z}/{x}/{y}.npy")
        if tile_count_cache_path.exists():
            try:
                tile_counts = np.load(tile_count_cache_path)
            except ValueError:
                logger.warning(
                    f"Heatmap count file {tile_count_cache_path} is corrupted, deleting."
                )
                tile_count_cache_path.unlink()
                tile_counts = np.zeros(tile_pixels, dtype=np.int32)
        tile_count_cache_path.parent.mkdir(parents=True, exist_ok=True)
        activity_ids = activities_per_tile[z].get((x, y), set())

        with work_tracker(
            tile_count_cache_path.with_suffix(".json")
        ) as parsed_activities:
            if parsed_activities - activity_ids:
                logger.warning(
                    f"Resetting heatmap cache for {x=}/{y=}/{z=} because activities have been removed."
                )
                tile_counts = np.zeros(tile_pixels, dtype=np.int32)
                parsed_activities.clear()
            for activity_id in list(activity_ids):
                if activity_id in parsed_activities:
                    continue
                parsed_activities.add(activity_id)
                time_series = repository.get_time_series(activity_id)
                for _, group in time_series.groupby("segment_id"):
                    xy_pixels = (
                        np.array([group["x"] * 2**z - x, group["y"] * 2**z - y]).T
                        * OSM_TILE_SIZE
                    )
                    im = Image.new("L", tile_pixels)
                    draw = ImageDraw.Draw(im)
                    pixels = list(map(int, xy_pixels.flatten()))
                    draw.line(pixels, fill=1, width=max(3, 6 * (z - 17)))
                    aim = np.array(im)
                    tile_counts += aim
        tmp_path = tile_count_cache_path.with_suffix(".tmp.npy")
        np.save(tmp_path, tile_counts)
        tile_count_cache_path.unlink(missing_ok=True)
        tmp_path.rename(tile_count_cache_path)
    else:
        activities = apply_search_query(repository.meta, query)
        activity_ids = activities_per_tile[z].get((x, y), set())
        for activity_id in activity_ids:
            if activity_id not in activities["id"]:
                continue
            time_series = repository.get_time_series(activity_id)
            for _, group in time_series.groupby("segment_id"):
                xy_pixels = (
                    np.array([group["x"] * 2**z - x, group["y"] * 2**z - y]).T
                    * OSM_TILE_SIZE
                )
                im = Image.new("L", tile_pixels)
                draw = ImageDraw.Draw(im)
                pixels = list(map(int, xy_pixels.flatten()))
                draw.line(pixels, fill=1, width=max(3, 6 * (z - 17)))
                aim = np.array(im)
                tile_counts += aim
    return tile_counts


def _render_tile_image(
    x: int,
    y: int,
    z: int,
    query: SearchQuery,
    config: Config,
    repository: ActivityRepository,
    activities_per_tile: dict[int, dict[tuple[int, int], set[int]]],
) -> np.ndarray:
    tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
    tile_counts = np.zeros(tile_pixels)
    tile_counts += _get_counts(x, y, z, query, repository, activities_per_tile)

    tile_counts = np.sqrt(tile_counts) / 5
    tile_counts[tile_counts > 1.0] = 1.0

    cmap = pl.get_cmap(config.color_scheme_for_heatmap)
    data_color = cmap(tile_counts)
    data_color[tile_counts > 0, 3] = 0.8
    data_color[tile_counts == 0, 3] = 0.0
    return data_color
