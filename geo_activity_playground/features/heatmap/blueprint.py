import datetime
import io
import logging
import pathlib
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import matplotlib.pylab as pl
import numpy as np
import sqlalchemy
from flask import Blueprint, Response, redirect, render_template, request, url_for
from flask_babel import gettext as _
from PIL import Image, ImageDraw

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB, StoredSearchQuery, UiConfig
from ...core.meta_search import (
    apply_search_filter,
    get_stored_queries,
    is_search_active,
    parse_search_params,
    primitives_to_jinja,
    primitives_to_json,
    primitives_to_url_str,
    register_search_query,
)
from ...core.raster_map import (
    OSM_TILE_SIZE,
    GeoBounds,
    PixelBounds,
    get_sensible_zoom_level,
)
from ...core.tiles import get_tile_upper_left_lat_lon
from ...explorer.tile_visits import (
    get_activity_ids_in_tile,
    get_biggest_cluster_members,
    get_tile_medians,
)
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.blueprints.explorer_blueprint import (
    geojson_bounding_box_for_tile_collection,
)
from ...webui.flasher import Flasher, FlashTypes
from .cache import (
    blob_to_counts,
    delete_all_heatmap_cache,
    delete_stale_heatmap_cache,
    get_tile_cache,
    write_tile_cache,
)
from .model import HeatmapTileCache

logger = logging.getLogger(__name__)


@contextmanager
def _handle_db_lock(message: str) -> Generator[None, None, None]:
    try:
        yield
    except sqlalchemy.exc.OperationalError:
        logger.warning(message)
        DB.session.rollback()


def make_heatmap_blueprint(
    repository: ActivityRepository,
    config_accessor: ConfigAccessor,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("heatmap", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        primitives = parse_search_params(request.args)

        if authenticator.is_authenticated():
            register_search_query(primitives)

        zoom = 14
        medians = get_tile_medians(zoom)
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians[0], medians[1], zoom
        )
        biggest_cluster_members = get_biggest_cluster_members(zoom)

        stored_queries = get_stored_queries()
        search_query_favorites = [
            (str(q), q.to_url_str()) for q in stored_queries if q.is_favorite
        ]
        search_query_last = [
            (str(q), q.to_url_str()) for q in stored_queries if not q.is_favorite
        ]

        context = {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": (
                    geojson_bounding_box_for_tile_collection(
                        biggest_cluster_members, zoom
                    )
                    if biggest_cluster_members
                    else {}
                ),
            },
            "extra_args": primitives_to_url_str(primitives),
            "query": primitives_to_jinja(primitives),
            "search_query_favorites": search_query_favorites,
            "search_query_last": search_query_last,
        }

        return render_template("heatmap/index.html.j2", **context)

    @blueprint.route("/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(x: int, y: int, z: int):
        primitives = parse_search_params(request.args)
        f = io.BytesIO()
        pl.imsave(
            f,
            _render_tile_image(
                x,
                y,
                z,
                primitives,
                config_accessor.ui(),
                repository,
            ),
            format="png",
        )
        return Response(
            bytes(f.getbuffer()),
            mimetype="image/png",
            headers={"Cache-Control": "no-cache"},
        )

    @blueprint.route(
        "/download/<float:north>/<float:east>/<float:south>/<float:west>/heatmap.png"
    )
    def download(north: float, east: float, south: float, west: float):
        primitives = parse_search_params(request.args)
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
                    primitives,
                    config_accessor.ui(),
                    repository,
                )

        f = io.BytesIO()
        pl.imsave(f, background, format="png")
        return Response(
            bytes(f.getbuffer()),
            mimetype="image/png",
            headers={
                "Content-disposition": 'attachment; filename="heatmap.png"',
                "Cache-Control": "no-cache",
            },
        )

    return blueprint


def register_heatmap_settings(
    blueprint: Blueprint, authenticator: Authenticator, flasher: Flasher
) -> None:
    """Register the heatmap cache maintenance route onto the settings blueprint."""

    @blueprint.route("/heatmap-cache", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def heatmap_cache():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "reset_heatmap_cache":
                logger.info("User requested reset of heatmap cache.")
                dropped = delete_all_heatmap_cache()
                heatmap_cache_dir = pathlib.Path("Cache/Heatmap")
                if heatmap_cache_dir.exists():
                    shutil.rmtree(heatmap_cache_dir)
                flasher.flash_message(
                    _("Heatmap cache has been cleared (%(dropped)s tiles).")
                    % {"dropped": dropped},
                    FlashTypes.SUCCESS,
                )
            elif action == "cleanup_heatmap_cache_stale":
                logger.info("User requested cleanup of stale heatmap cache.")
                cutoff = datetime.datetime.now() - datetime.timedelta(days=182)
                dropped = delete_stale_heatmap_cache(cutoff)
                flasher.flash_message(
                    _(
                        "Dropped %(dropped)s stale heatmap cache tiles (unused for six months)."
                    )
                    % {"dropped": dropped},
                    FlashTypes.SUCCESS,
                )
            return redirect(url_for(".heatmap_cache"))

        total_tiles, stats = _heatmap_cache_stats()
        return render_template(
            "settings/heatmap-cache.html.j2",
            heatmap_cache_total_tiles=total_tiles,
            heatmap_cache_stats=stats,
        )


def _heatmap_cache_stats() -> tuple[int, list[dict[str, Any]]]:
    grouped_rows = DB.session.execute(
        sqlalchemy.select(
            HeatmapTileCache.search_query_id,
            sqlalchemy.func.count(HeatmapTileCache.id).label("num_tiles"),
            sqlalchemy.func.sum(HeatmapTileCache.num_activities).label(
                "num_activities"
            ),
            sqlalchemy.func.max(HeatmapTileCache.last_used).label("last_used"),
        )
        .group_by(HeatmapTileCache.search_query_id)
        .order_by(
            HeatmapTileCache.search_query_id.is_not(None),
            HeatmapTileCache.search_query_id,
        )
    ).all()

    query_ids = [
        row.search_query_id for row in grouped_rows if row.search_query_id is not None
    ]
    query_by_id = {
        query.id: query
        for query in DB.session.scalars(
            sqlalchemy.select(StoredSearchQuery).where(
                StoredSearchQuery.id.in_(query_ids)
            )
        ).all()
    }

    stats: list[dict[str, Any]] = []
    total_tiles = 0
    for row in grouped_rows:
        search_query_id = row.search_query_id
        num_tiles = int(row.num_tiles or 0)
        num_activities = int(row.num_activities or 0)
        total_tiles += num_tiles

        if search_query_id is None:
            description = _("No search query")
            is_favorite = None
        else:
            query = query_by_id.get(search_query_id)
            if query:
                description = str(query)
                is_favorite = query.is_favorite
            else:
                description = _("Deleted search query #%d") % search_query_id
                is_favorite = False

        stats.append(
            {
                "search_query_id": search_query_id,
                "description": description,
                "num_tiles": num_tiles,
                "num_activities": num_activities,
                "last_used": row.last_used,
                "is_favorite": is_favorite,
            }
        )
    return total_tiles, stats


def _get_counts(
    x: int,
    y: int,
    z: int,
    primitives: dict,
    config: UiConfig,
    repository: ActivityRepository,
) -> np.ndarray:
    tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
    tile_counts = np.zeros(tile_pixels, dtype=np.int32)
    activity_ids = get_activity_ids_in_tile(z, x, y)

    search_query_id: int | None = None
    should_use_cache = True
    if is_search_active(primitives):
        activities = apply_search_filter(primitives)
        matching_activity_ids = set(activities["id"].tolist())
        activity_ids = activity_ids & matching_activity_ids
        search_query_id = _favorite_search_query_id(primitives)
        should_use_cache = search_query_id is not None

    if should_use_cache:
        parsed_activities: set[int] = set()
        cache_entry = None
        with _handle_db_lock(
            f"Failed to read heatmap cache for {x=}/{y=}/{z=}, recomputing."
        ):
            cache_entry = get_tile_cache(
                zoom=z, tile_x=x, tile_y=y, search_query_id=search_query_id
            )
        if cache_entry:
            try:
                tile_counts = blob_to_counts(cache_entry.counts).astype(
                    np.int32, copy=False
                )
                if tile_counts.shape != tile_pixels:
                    raise ValueError("invalid tile shape in cache")
                parsed_activities = set(cache_entry.included_activity_ids or [])
            except ValueError:
                logger.warning(
                    f"Resetting corrupted heatmap cache for {x=}/{y=}/{z=}/{search_query_id=}."
                )
                tile_counts = np.zeros(tile_pixels, dtype=np.int32)
                parsed_activities = set()

        if parsed_activities - activity_ids:
            logger.warning(
                f"Resetting heatmap cache for {x=}/{y=}/{z=}/{search_query_id=} because activities have been removed."
            )
            tile_counts = np.zeros(tile_pixels, dtype=np.int32)
            parsed_activities.clear()

        for activity_id in activity_ids:
            if activity_id in parsed_activities:
                continue
            time_series = None
            with _handle_db_lock(
                f"Skipping activity {activity_id} for {x=}/{y=}/{z=} due to DB error."
            ):
                try:
                    time_series = repository.get_time_series(activity_id)
                except ValueError:
                    logger.warning(
                        f"Skipping deleted activity {activity_id} for {x=}/{y=}/{z=}."
                    )
            if time_series is None:
                continue
            parsed_activities.add(activity_id)
            _paint_activity(tile_counts, time_series, x=x, y=y, z=z)

        with _handle_db_lock(
            f"Failed to write heatmap cache for {x=}/{y=}/{z=}, skipping."
        ):
            write_tile_cache(
                zoom=z,
                tile_x=x,
                tile_y=y,
                search_query_id=search_query_id,
                counts=tile_counts,
                included_activity_ids=parsed_activities,
                min_activities=config.heatmap_cache_min_activities,
            )
    else:
        for activity_id in activity_ids:
            try:
                time_series = repository.get_time_series(activity_id)
            except ValueError:
                logger.warning(
                    f"Skipping deleted activity {activity_id} for {x=}/{y=}/{z=}."
                )
                continue
            _paint_activity(tile_counts, time_series, x=x, y=y, z=z)
    return tile_counts


def _favorite_search_query_id(primitives: dict) -> int | None:
    query_json = primitives_to_json(primitives)
    return DB.session.scalar(
        sqlalchemy.select(StoredSearchQuery.id).where(
            StoredSearchQuery.query_json == query_json,
            StoredSearchQuery.is_favorite.is_(True),
        )
    )


def _paint_activity(
    tile_counts: np.ndarray, time_series, *, x: int, y: int, z: int
) -> None:
    tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
    for _segment_id, group in time_series.groupby("segment_id"):
        xy_pixels = (
            np.array([group["x"] * 2**z - x, group["y"] * 2**z - y]).T * OSM_TILE_SIZE
        )
        im = Image.new("L", tile_pixels)
        draw = ImageDraw.Draw(im)
        pixels = list(map(int, xy_pixels.flatten()))
        draw.line(pixels, fill=1, width=max(3, 6 * (z - 17)))
        aim = np.array(im)
        tile_counts += aim


def _render_tile_image(
    x: int,
    y: int,
    z: int,
    primitives: dict,
    config: UiConfig,
    repository: ActivityRepository,
) -> np.ndarray:
    tile_pixels = (OSM_TILE_SIZE, OSM_TILE_SIZE)
    tile_counts = np.zeros(tile_pixels)
    tile_counts += _get_counts(x, y, z, primitives, config, repository)

    tile_counts = np.sqrt(tile_counts) / 5
    tile_counts[tile_counts > 1.0] = 1.0

    cmap = pl.get_cmap(config.color_scheme_for_heatmap)
    data_color = cmap(tile_counts)
    data_color[tile_counts > 0, 3] = 0.8
    data_color[tile_counts == 0, 3] = 0.0
    return data_color
