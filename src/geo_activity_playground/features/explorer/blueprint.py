import io
import json
import re
from types import SimpleNamespace
from typing import Any

import altair as alt
import geojson
import matplotlib.pyplot as pl
import numpy as np
import pandas as pd
import requests
import sqlalchemy
from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...core.coordinates import Bounds
from ...core.datamodel import (
    DB,
    Activity,
    TileVisit,
    apply_privacy_zones_to_tracks_if_enabled,
)
from ...core.grid import (
    geojson_bounding_box_for_tile_collection,
    get_border_tiles,
    make_explorer_tile,
    make_grid_file_geojson,
    make_grid_file_gpx,
    make_grid_file_kml,
    make_grid_file_kml_squadrats,
    make_grid_file_osm,
    make_grid_points,
)
from ...core.meta_search import (
    activity_ids_for_search,
    is_search_active,
    parse_search_params,
)
from ...core.raster_map import OSM_TILE_SIZE, ImageTransform, TileGetter
from ...core.tile_visits import (
    get_activity_ids_in_bounds,
    get_latest_new_tiles_day,
    get_new_tiles_activity_ids_on_day,
    get_tile_count,
    get_tile_history_df,
    get_tile_medians,
    get_tile_visits_in_bounds,
)
from ...core.tiles import compute_tile, get_tile_upper_left_lat_lon
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.plot_util import to_vega
from ...webui.search_context import search_context
from .clustering import (
    compute_current_state_for_zoom,
    compute_tile_evolution,
    get_biggest_cluster_members,
    get_cluster_history_latest_event_index,
    get_cluster_id_for_tile,
    get_cluster_members,
    get_cluster_size_history_df,
    get_cluster_state_at_cutoff,
    get_cluster_tile_count,
    get_cluster_tiles_at_cutoff,
    get_cluster_tiles_gained_by_activity,
    get_explorer_square,
    get_max_cluster,
    get_square_history_df,
    is_cluster_history_stale,
    mark_cluster_history_stale,
    rebuild_cluster_history_if_stale,
)
from .filtered import (
    delete_filtered_cluster_cache,
    get_filtered_cluster_state,
    get_filtered_tile_visits_in_bounds,
    get_filtered_visited_tiles,
)
from .garmin_img import build_garmin_img, mkgmap_available
from .inaccessible import get_inaccessible_tiles
from .model import (
    TRANSPARENT,
    BorderStroke,
    ExplorerTileBookmark,
    InaccessibleTile,
)
from .tile_rendering import (
    TileStyleSpec,
    _render_tile_image,
    _resolve_color_strategy,
    _tile_bounds,
    hex_color_to_tuple,
    render_activity_lines_tile_image,
    render_inaccessible_tile_image,
    render_tile_style_preview,
)

HEX_RGBA = re.compile(r"^#[0-9a-fA-F]{8}$")

alt.data_transformers.enable("vegafusion")


def _grid_points_response(
    points: list[list[tuple[float, float]]], suffix: str, name: str
) -> ResponseReturnValue:
    if suffix == "geojson":
        return Response(
            make_grid_file_geojson(points),
            mimetype="application/json",
            headers={"Content-disposition": "attachment"},
        )
    elif suffix == "gpx":
        return Response(
            make_grid_file_gpx(points),
            mimetype="application/xml",
            headers={"Content-disposition": "attachment"},
        )
    elif suffix == "kml":
        return Response(
            make_grid_file_kml(points),
            mimetype="application/vnd.google-earth.kml+xml",
            headers={"Content-disposition": "attachment"},
        )
    elif suffix == "img":
        if not mkgmap_available():
            abort(404)
        return Response(
            build_garmin_img(make_grid_file_osm(points), name),
            mimetype="application/octet-stream",
            headers={
                "Content-disposition": f"attachment; filename={name}-gmapsupp.img"
            },
        )
    else:
        abort(404)


def _png_response(image: np.ndarray) -> ResponseReturnValue:
    f = io.BytesIO()
    pl.imsave(f, image, format="png")
    return Response(
        bytes(f.getbuffer()),
        mimetype="image/png",
        headers={"Cache-Control": "no-cache"},
    )


def _explorer_layer(zoom: int, color_strategy: str) -> tuple[str, dict, dict]:
    source_id = f"gap-explorer-{zoom}-{color_strategy}"
    source = {
        "type": "raster",
        "tiles": [
            f"/explorer/{zoom}/tile/{{z}}/{{x}}/{{y}}.png"
            f"?color_strategy={color_strategy}"
        ],
        "tileSize": 256,
    }
    layer = {
        "id": f"gap-explorer-layer-{zoom}-{color_strategy}",
        "type": "raster",
        "source": source_id,
        "paint": {"raster-opacity": 0.8},
    }
    return source_id, source, layer


def _inaccessible_layer(zoom: int) -> tuple[str, dict, dict]:
    source_id = f"gap-inaccessible-{zoom}"
    source = {
        "type": "raster",
        "tiles": [f"/explorer/{zoom}/inaccessible-tile/{{z}}/{{x}}/{{y}}.png"],
        "tileSize": 256,
    }
    layer = {
        "id": f"gap-inaccessible-layer-{zoom}",
        "type": "raster",
        "source": source_id,
        "paint": {"raster-opacity": 0.8},
    }
    return source_id, source, layer


def _latest_new_tiles_activity_layer(zoom: int) -> tuple[str, dict, dict]:
    source_id = f"gap-latest-new-tiles-activity-{zoom}"
    source = {
        "type": "raster",
        "tiles": [f"/explorer/{zoom}/latest-new-tiles-activity/{{z}}/{{x}}/{{y}}.png"],
        "tileSize": 256,
    }
    layer = {
        "id": f"gap-latest-new-tiles-activity-layer-{zoom}",
        "type": "raster",
        "source": source_id,
        "paint": {"raster-opacity": 0.8},
    }
    return source_id, source, layer


def _parse_layer_specs(raw_layers: str) -> list[tuple[int, str]]:
    specs = []
    for token in raw_layers.split(","):
        token = token.strip()
        if not token:
            continue
        zoom_str, _, kind = token.partition(":")
        specs.append((int(zoom_str), kind or "colorful_cluster"))
    return specs


def _build_style(
    config_accessor: ConfigAccessor,
    sources: dict[str, Any],
    layers: list[dict[str, Any]],
) -> dict[str, Any]:
    map_style_url = config_accessor.map().map_style_url
    if map_style_url:
        style = requests.get(map_style_url, timeout=10).json()
        style["sources"].update(sources)
        style["layers"].extend(layers)
    else:
        raster_tile_url = config_accessor.map().map_tile_url.replace("{zoom}", "{z}")
        style = {
            "version": 8,
            "sources": {
                "base-map": {
                    "type": "raster",
                    "tiles": [raster_tile_url],
                    "tileSize": 256,
                },
                **sources,
            },
            "layers": [
                {"id": "base-map-layer", "type": "raster", "source": "base-map"},
                *layers,
            ],
        }
    return style


def make_explorer_blueprint(
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
    tile_getter: TileGetter,
    image_transforms: dict[str, ImageTransform],
) -> Blueprint:
    blueprint = Blueprint("explorer", __name__, template_folder="templates")

    @blueprint.route("/enable-zoom-level/<int:zoom>", methods=["POST"])
    @needs_authentication(authenticator)
    def enable_zoom_level(zoom: int) -> ResponseReturnValue:
        if 0 <= zoom <= 19:
            ui_config = config_accessor.ui()
            if zoom not in ui_config.explorer_zoom_levels:
                ui_config.explorer_zoom_levels.append(zoom)
                ui_config.explorer_zoom_levels.sort()
                config_accessor.save()
                compute_tile_evolution(ui_config, [zoom])
            flash(f"Enabled {zoom=} for explorer tiles.", category="success")
        else:
            flash(f"{zoom=} is not valid, must be between 0 and 19.", category="danger")
        return redirect(url_for(".map", zoom=zoom))

    @blueprint.route(
        "/<int:zoom>/<float(signed=True):north>/<float(signed=True):east>/<float(signed=True):south>/<float(signed=True):west>/missing.<suffix>"
    )
    def download_missing(
        zoom: int, north: float, east: float, south: float, west: float, suffix: str
    ) -> ResponseReturnValue:
        x1, y1 = compute_tile(north, west, zoom)
        x2, y2 = compute_tile(south, east, zoom)
        tile_bounds = Bounds(x1, y1, x2 + 2, y2 + 2)

        tiles = get_tile_history_df(zoom)
        excluded_tiles = get_inaccessible_tiles(
            zoom,
            tile_bounds.x_min,
            tile_bounds.x_max,
            tile_bounds.y_min,
            tile_bounds.y_max,
        )
        points = get_border_tiles(tiles, zoom, tile_bounds, excluded_tiles)
        return _grid_points_response(points, suffix, "missing")

    @blueprint.route(
        "/<int:zoom>/<float(signed=True):north>/<float(signed=True):east>/<float(signed=True):south>/<float(signed=True):west>/explored.<suffix>"
    )
    def download_explored(
        zoom: int, north: float, east: float, south: float, west: float, suffix: str
    ) -> ResponseReturnValue:
        x1, y1 = compute_tile(north, west, zoom)
        x2, y2 = compute_tile(south, east, zoom)
        tile_bounds = Bounds(x1, y1, x2 + 2, y2 + 2)

        tiles = get_tile_visits_in_bounds(zoom, x1, x2 + 2, y1, y2 + 2)
        points = make_grid_points(
            (tile for tile in tiles.keys() if tile_bounds.contains(*tile)), zoom
        )
        return _grid_points_response(points, suffix, "explored")

    @blueprint.route(
        "/<int:zoom>/<float(signed=True):north>/<float(signed=True):east>/<float(signed=True):south>/<float(signed=True):west>/inaccessible.<suffix>"
    )
    def download_inaccessible(
        zoom: int, north: float, east: float, south: float, west: float, suffix: str
    ) -> ResponseReturnValue:
        x1, y1 = compute_tile(north, west, zoom)
        x2, y2 = compute_tile(south, east, zoom)

        inaccessible_tiles = get_inaccessible_tiles(zoom, x1, x2 + 2, y1, y2 + 2)
        points = make_grid_points(inaccessible_tiles, zoom)
        return _grid_points_response(points, suffix, "inaccessible")

    @blueprint.route("/squadrats.kml")
    def download_squadrats() -> ResponseReturnValue:
        explored: dict[int, list[tuple[int, int]]] = {}
        squares: dict[int, tuple[int, int, int]] = {}
        for zoom in (14, 17):
            tiles = get_tile_history_df(zoom)
            if len(tiles):
                explored[zoom] = list(zip(tiles["tile_x"], tiles["tile_y"]))
            square_x, square_y, square_size = get_explorer_square(zoom)
            if square_x is not None and square_size:
                squares[zoom] = (square_x, square_y, square_size)
        if not explored:
            abort(404)
        return Response(
            make_grid_file_kml_squadrats(explored, squares),
            mimetype="application/vnd.google-earth.kml+xml",
            headers={"Content-disposition": "attachment; filename=squadrats.kml"},
        )

    @blueprint.route("/<int:zoom>/server-side")
    def server_side(zoom: int) -> ResponseReturnValue:
        if zoom not in config_accessor.ui().explorer_zoom_levels:
            return {"zoom_level_not_generated": zoom}

        primitives, search_vars = search_context(authenticator)
        search_active = is_search_active(primitives)

        # Get data from database
        medians = get_tile_medians(zoom)
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians[0], medians[1], zoom
        )

        if search_active:
            activity_ids = frozenset(activity_ids_for_search(primitives) or ())
            filtered = get_filtered_cluster_state(zoom, activity_ids)
            square_x = filtered.square_x
            square_y = filtered.square_y
            square_size = filtered.max_square_size
            num_tiles = len(get_filtered_visited_tiles(zoom, activity_ids))
            num_cluster_tiles = filtered.num_cluster_tiles
            max_cluster_size = filtered.max_cluster_size
            biggest_cluster_members = [
                tile
                for tile, root in filtered.membership.items()
                if root == filtered.max_cluster_id
            ]
        else:
            square_x, square_y, square_size = get_explorer_square(zoom)
            num_tiles = get_tile_count(zoom)
            num_cluster_tiles = get_cluster_tile_count(zoom)
            _representative, max_cluster_size = get_max_cluster(zoom)
            biggest_cluster_members = get_biggest_cluster_members(zoom)

        bookmarks: list[dict[str, Any]] = []
        for bookmark in DB.session.scalars(
            sqlalchemy.select(ExplorerTileBookmark).where(
                ExplorerTileBookmark.zoom == zoom
            )
        ).all():
            tile = (bookmark.tile_x, bookmark.tile_y)
            representative = get_cluster_id_for_tile(zoom, tile[0], tile[1])
            if representative is None:
                continue
            cluster = get_cluster_members(zoom, representative[0], representative[1])
            if not cluster:
                continue
            bookmarks.append(
                {
                    "id": bookmark.id,
                    "name": bookmark.name,
                    "bbox": geojson_bounding_box_for_tile_collection(cluster, zoom),
                    "size": len(cluster),
                }
            )

        context = {
            "center": {
                "latitude": median_lat,
                "longitude": median_lon,
                "bbox": (
                    geojson_bounding_box_for_tile_collection(
                        biggest_cluster_members, zoom
                    )
                    if biggest_cluster_members
                    else None
                ),
            },
            "history_stale": is_cluster_history_stale(zoom),
            "search_active": search_active,
            **search_vars,
            "zoom": zoom,
            "num_tiles": num_tiles,
            "num_cluster_tiles": num_cluster_tiles,
            "square_x": square_x,
            "square_y": square_y,
            "square_size": square_size,
            "max_cluster_size": max_cluster_size,
            "bookmarks": bookmarks,
            "mkgmap_available": mkgmap_available(),
            "zoom_level_not_generated": None,
        }
        return render_template("explorer/server-side.html.j2", **context)

    @blueprint.route("/<int:zoom>/evolution/<plot>.json")
    def evolution_plot(zoom: int, plot: str) -> ResponseReturnValue:
        """One evolution plot, replaying the history first if it is outdated.

        The explorer page fetches these after rendering so that a rebuild does
        not hold up the page itself.
        """
        if plot not in ("tiles", "cluster", "square"):
            abort(404)
        rebuild_cluster_history_if_stale(zoom)
        match plot:
            case "tiles":
                spec = plot_tile_evolution(get_tile_history_df(zoom))
            case "cluster":
                spec = plot_cluster_evolution(get_cluster_size_history_df(zoom))
            case "square":
                spec = plot_square_evolution(get_square_history_df(zoom))
        return {"spec": json.loads(spec) if spec else None}

    @blueprint.after_request
    def add_cors_headers(response: Response) -> Response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @blueprint.route("/<int:zoom>/style.json")
    def style_json(zoom: int) -> ResponseReturnValue:
        color_strategy = request.args.get("color_strategy", "colorful_cluster")
        source_id, source, layer = _explorer_layer(zoom, color_strategy)
        inaccessible_source_id, inaccessible_source, inaccessible_layer = (
            _inaccessible_layer(zoom)
        )
        style = _build_style(
            config_accessor,
            {source_id: source, inaccessible_source_id: inaccessible_source},
            [layer, inaccessible_layer],
        )
        return Response(json.dumps(style), mimetype="application/json")

    @blueprint.route("/style.json")
    def combined_style_json() -> ResponseReturnValue:
        raw_layers = request.args.get("layers")
        if raw_layers:
            layer_specs = _parse_layer_specs(raw_layers)
        else:
            zoom_levels = sorted(config_accessor.ui().explorer_zoom_levels)
            layer_specs = [(zoom, "colorful_cluster") for zoom in zoom_levels] + [
                (zoom, "inaccessible") for zoom in zoom_levels
            ]

        sources: dict[str, Any] = {}
        layers: list[dict[str, Any]] = []
        for zoom, kind in layer_specs:
            if kind == "inaccessible":
                source_id, source, layer = _inaccessible_layer(zoom)
            elif kind == "latest_new_activity":
                source_id, source, layer = _latest_new_tiles_activity_layer(zoom)
            else:
                source_id, source, layer = _explorer_layer(zoom, kind)
            sources[source_id] = source
            layers.append(layer)

        style = _build_style(config_accessor, sources, layers)
        return Response(json.dumps(style), mimetype="application/json")

    @blueprint.route("/<int:zoom>/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(zoom: int, z: int, x: int, y: int) -> ResponseReturnValue:
        config = config_accessor.ui()
        tile_bounds = _tile_bounds(zoom, z, x, y)

        # An active search restricts which activities count, so tile visits,
        # clusters and the square all have to be derived for that filter
        # instead of read from the stored state.
        primitives = parse_search_params(request.args)
        filtered_activity_ids = (
            frozenset(activity_ids_for_search(primitives) or ())
            if is_search_active(primitives)
            else None
        )
        filtered_state = None

        if filtered_activity_ids is None:
            square_x, square_y, square_size = get_explorer_square(zoom)
            tile_visits = get_tile_visits_in_bounds(
                zoom,
                tile_bounds.x_min,
                tile_bounds.x_max,
                tile_bounds.y_min,
                tile_bounds.y_max,
            )
        else:
            filtered_state = get_filtered_cluster_state(zoom, filtered_activity_ids)
            square_x = filtered_state.square_x
            square_y = filtered_state.square_y
            square_size = filtered_state.max_square_size
            tile_visits = get_filtered_tile_visits_in_bounds(
                zoom, tile_bounds, filtered_activity_ids
            )

        evolution_state = SimpleNamespace(
            square_x=square_x, square_y=square_y, max_square_size=square_size
        )

        # The history describes the unfiltered set only, so the time slider and
        # a search filter are mutually exclusive.
        history_event_index = request.args.get("event_index", type=int)
        historical_state = None
        if history_event_index is not None and filtered_activity_ids is None:
            history_event_index = max(
                0,
                min(history_event_index, get_cluster_history_latest_event_index(zoom)),
            )
            historical_state = get_cluster_state_at_cutoff(zoom, history_event_index)

        inaccessible_tiles = get_inaccessible_tiles(
            zoom,
            tile_bounds.x_min,
            tile_bounds.x_max,
            tile_bounds.y_min,
            tile_bounds.y_max,
        )
        color_strategy = _resolve_color_strategy(
            request,
            zoom,
            tile_visits,
            tile_bounds.x_min,
            tile_bounds.x_max,
            tile_bounds.y_min,
            tile_bounds.y_max,
            historical_state,
            config,
            filtered_state,
            inaccessible_tiles,
        )

        result = _render_tile_image(
            zoom, z, x, y, color_strategy, evolution_state, config
        )
        return _png_response(result)

    @blueprint.route("/tile-style-preview.png")
    def tile_style_preview() -> ResponseReturnValue:
        colors = {
            key: request.args.get(key, TRANSPARENT)
            for key in ("fill_color", "border_color", "stripe_color")
        }
        if not all(HEX_RGBA.match(color) for color in colors.values()):
            abort(400)
        spec = TileStyleSpec(
            fill_color=hex_color_to_tuple(colors["fill_color"]),
            border_color=hex_color_to_tuple(colors["border_color"]),
            border_width=request.args.get("border_width", 0, type=int),
            border_dashed=request.args.get("border_stroke") == BorderStroke.DASHED,
            stripe_color=hex_color_to_tuple(colors["stripe_color"]),
        )
        return _png_response(render_tile_style_preview(spec))

    @blueprint.route(
        "/<int:zoom>/latest-new-tiles-activity/<int:z>/<int:x>/<int:y>.png"
    )
    def latest_new_tiles_activity_tile(
        zoom: int, z: int, x: int, y: int
    ) -> ResponseReturnValue:
        empty = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE, 4), dtype=np.float32)
        requested_id = request.args.get("activity_id", type=int)
        if requested_id is not None:
            activity_ids = {requested_id}
        else:
            day = get_latest_new_tiles_day(zoom)
            activity_ids = (
                set(get_new_tiles_activity_ids_on_day(zoom, day))
                if day is not None
                else set()
            )
        if not activity_ids:
            return _png_response(empty)

        # The activity tiles tell us cheaply which tracks can be visible here at
        # all, which spares us reading their time series for most tiles.
        tile_bounds = _tile_bounds(zoom, z, x, y)
        activity_ids &= get_activity_ids_in_bounds(
            zoom,
            tile_bounds.x_min,
            tile_bounds.x_max,
            tile_bounds.y_min,
            tile_bounds.y_max,
        )
        if not activity_ids:
            return _png_response(empty)

        activities = [
            activity
            for activity_id in sorted(activity_ids)
            if (activity := DB.session.get(Activity, activity_id)) is not None
        ]
        if not activities:
            return _png_response(empty)
        ui_config = config_accessor.ui()
        return _png_response(
            render_activity_lines_tile_image(
                (
                    apply_privacy_zones_to_tracks_if_enabled(
                        activity.time_series, ui_config
                    )
                    for activity in activities
                ),
                z,
                x,
                y,
                ui_config.activity_line_color,
            )
        )

    @blueprint.route("/<int:zoom>/inaccessible-tile/<int:z>/<int:x>/<int:y>.png")
    def inaccessible_tile(zoom: int, z: int, x: int, y: int) -> ResponseReturnValue:
        tile_bounds = _tile_bounds(zoom, z, x, y)
        inaccessible_tiles = get_inaccessible_tiles(
            zoom,
            tile_bounds.x_min,
            tile_bounds.x_max,
            tile_bounds.y_min,
            tile_bounds.y_max,
        )
        return _png_response(
            render_inaccessible_tile_image(zoom, z, x, y, inaccessible_tiles)
        )

    @blueprint.route(
        "/<int:zoom>/info/<float(signed=True):latitude>/<float(signed=True):longitude>"
    )
    def info(zoom: int, latitude: float, longitude: float) -> str:
        _square_x, _square_y, square_size = get_explorer_square(zoom)
        tile_xy = compute_tile(latitude, longitude, zoom)
        cluster_id = get_cluster_id_for_tile(zoom, tile_xy[0], tile_xy[1])
        is_inaccessible = (
            DB.session.query(InaccessibleTile)
            .filter_by(
                zoom=zoom,
                tile_x=tile_xy[0],
                tile_y=tile_xy[1],
            )
            .first()
            is not None
        )
        context: dict[str, Any] = {
            "tile_x": tile_xy[0],
            "tile_y": tile_xy[1],
            "zoom": zoom,
            "square_size": square_size,
            "is_inaccessible": is_inaccessible,
            "num_visits": 0,
            "this_cluster_size": 0,
            "new_bookmark_url": None,
            "activities_through_tile_url": None,
            "unmark_url": None,
            "mark_url": None,
        }

        # Query tile info from database
        tile_visit = (
            DB.session.query(TileVisit)
            .filter(
                TileVisit.zoom == zoom,
                TileVisit.tile_x == tile_xy[0],
                TileVisit.tile_y == tile_xy[1],
            )
            .first()
        )

        if tile_visit is not None:
            context.update(
                {
                    "num_visits": tile_visit.visit_count,
                    "first_activity_id": tile_visit.first_activity_id,
                    "first_activity_name": tile_visit.first_activity.name,
                    "first_time": (
                        tile_visit.first_time.isoformat()
                        if tile_visit.first_time
                        else None
                    ),
                    "last_activity_id": tile_visit.last_activity_id,
                    "last_activity_name": tile_visit.last_activity.name,
                    "last_time": (
                        tile_visit.last_time.isoformat()
                        if tile_visit.last_time
                        else None
                    ),
                    "is_cluster": cluster_id is not None,
                    "this_cluster_size": (
                        len(get_cluster_members(zoom, cluster_id[0], cluster_id[1]))
                        if cluster_id is not None
                        else 0
                    ),
                    "new_bookmark_url": url_for(
                        "settings.cluster_bookmark_new",
                        zoom=zoom,
                        tile_x=tile_xy[0],
                        tile_y=tile_xy[1],
                    ),
                    "activities_through_tile_url": url_for(
                        ".activities_through_tile",
                        zoom=zoom,
                        tile_x=tile_xy[0],
                        tile_y=tile_xy[1],
                        radius=0,
                    ),
                }
            )
        if is_inaccessible:
            context["unmark_url"] = url_for(
                ".remove_inaccessible",
                zoom=zoom,
                tile_x=tile_xy[0],
                tile_y=tile_xy[1],
            )
        elif tile_visit is None:
            context["mark_url"] = url_for(
                ".mark_inaccessible",
                zoom=zoom,
                tile_x=tile_xy[0],
                tile_y=tile_xy[1],
            )
        return render_template("explorer/tooltip.html.j2", **context)

    @blueprint.route("/<int:zoom>/activities/<int:tile_x>/<int:tile_y>/<int:radius>")
    def activities_through_tile(
        zoom: int, tile_x: int, tile_y: int, radius: int
    ) -> ResponseReturnValue:
        """List all activities that pass through a tile or its vicinity.

        Args:
            zoom: The tile zoom level.
            tile_x: The tile X coordinate.
            tile_y: The tile Y coordinate.
            radius: The radius of neighboring tiles to include (0 = just this tile).
        """
        # Collect all activity IDs from the tile and its neighbors within the radius
        activity_ids = get_activity_ids_in_bounds(
            zoom,
            tile_x - radius,
            tile_x + radius,
            tile_y - radius,
            tile_y + radius,
        )

        # Fetch activities from database
        activities = []
        if activity_ids:
            activities = (
                DB.session.query(Activity)
                .filter(Activity.id.in_(activity_ids))
                .order_by(Activity.start.desc())
                .all()
            )

        context = {
            "zoom": zoom,
            "tile_x": tile_x,
            "tile_y": tile_y,
            "radius": radius,
            "activities": activities,
            "num_activities": len(activities),
        }
        return render_template("explorer/activities_through_tile.html.j2", **context)

    @blueprint.route("/<int:zoom>/cluster-history/snapshot.geojson")
    def cluster_history_snapshot(zoom: int) -> ResponseReturnValue:
        latest_event_index = get_cluster_history_latest_event_index(zoom)
        cutoff = request.args.get("event_index", type=int)
        if cutoff is None:
            cutoff = latest_event_index
        cutoff = max(0, min(cutoff, latest_event_index))
        cluster_tiles = get_cluster_tiles_at_cutoff(zoom, cutoff)
        geojson_str = make_grid_file_geojson(make_grid_points(cluster_tiles, zoom))
        return Response(geojson_str, mimetype="application/json")

    @blueprint.route("/<int:zoom>/cluster-history/metadata.json")
    def cluster_history_metadata(zoom: int) -> dict[str, int]:
        return {
            "latest_event_index": get_cluster_history_latest_event_index(zoom),
        }

    @blueprint.route(
        "/<int:zoom>/cluster-history/activity/<int:activity_id>/diff.geojson"
    )
    def cluster_history_activity_diff(
        zoom: int, activity_id: int
    ) -> ResponseReturnValue:
        added = get_cluster_tiles_gained_by_activity(zoom, activity_id)
        features = [
            make_explorer_tile(
                tile_x=tile_x,
                tile_y=tile_y,
                properties={"delta": "added"},
                zoom=zoom,
            )
            for tile_x, tile_y in sorted(added)
        ]
        return Response(
            geojson.dumps(geojson.FeatureCollection(features)),
            mimetype="application/json",
        )

    @blueprint.route(
        "/<int:zoom>/inaccessible/<int:tile_x>/<int:tile_y>", methods=["POST"]
    )
    @needs_authentication(authenticator)
    def mark_inaccessible(zoom: int, tile_x: int, tile_y: int) -> ResponseReturnValue:
        tile_visit = (
            DB.session.query(TileVisit)
            .filter_by(zoom=zoom, tile_x=tile_x, tile_y=tile_y)
            .first()
        )
        if tile_visit is not None:
            flash(
                _("Only missing tiles can be marked as inaccessible."),
                category="danger",
            )
            return redirect(url_for(".server_side", zoom=zoom))
        existing = (
            DB.session.query(InaccessibleTile)
            .filter_by(zoom=zoom, tile_x=tile_x, tile_y=tile_y)
            .first()
        )
        if existing is not None:
            flash(_("Tile is already marked as inaccessible."), category="warning")
        else:
            DB.session.add(
                InaccessibleTile(zoom=zoom, tile_x=tile_x, tile_y=tile_y)  # pyright: ignore
            )
            DB.session.commit()
            _refresh_after_inaccessible_change(zoom)
            flash(_("Tile marked as inaccessible."), category="success")
        return redirect(url_for(".server_side", zoom=zoom))

    @blueprint.route(
        "/<int:zoom>/inaccessible/<int:tile_x>/<int:tile_y>/remove", methods=["POST"]
    )
    @needs_authentication(authenticator)
    def remove_inaccessible(zoom: int, tile_x: int, tile_y: int) -> ResponseReturnValue:
        existing = (
            DB.session.query(InaccessibleTile)
            .filter_by(zoom=zoom, tile_x=tile_x, tile_y=tile_y)
            .first()
        )
        if existing is not None:
            DB.session.delete(existing)
            DB.session.commit()
            _refresh_after_inaccessible_change(zoom)
            flash(_("Tile unmarked as inaccessible."), category="success")
        else:
            flash(_("Tile was not marked as inaccessible."), category="warning")
        return redirect(url_for(".server_side", zoom=zoom))

    return blueprint


def _refresh_after_inaccessible_change(zoom: int) -> None:
    """React to a changed inaccessible tile set.

    The current cluster and square are cheap to recompute, so that happens
    right away. The history is not, so it is only flagged and replayed when a
    page asks for it.
    """
    if not ConfigAccessor().ui().count_inaccessible_in_cluster:
        return
    compute_current_state_for_zoom(zoom)
    delete_filtered_cluster_cache()
    mark_cluster_history_stale([zoom])


def plot_tile_evolution(tiles: pd.DataFrame) -> str:
    if len(tiles) == 0:
        return ""
    tiles["count"] = np.arange(1, len(tiles) + 1)
    return to_vega(
        alt.Chart(tiles, title=_("Tiles"))
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Time")), alt.Y("count", title=_("Number of tiles"))
        )
        .interactive(bind_y=False)
    )


def plot_cluster_evolution(cluster_evolution: pd.DataFrame) -> str:
    if len(cluster_evolution) == 0:
        return ""
    return to_vega(
        alt.Chart(cluster_evolution, title=_("Cluster"))
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("max_cluster_size", title=_("Maximum cluster size")),
        )
        .interactive(bind_y=False)
    )


def plot_square_evolution(square_evolution: pd.DataFrame) -> str:
    if len(square_evolution) == 0:
        return ""
    return to_vega(
        alt.Chart(square_evolution, title=_("Square"))
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("max_square_size", title=_("Maximum square size")),
        )
        .interactive(bind_y=False)
    )
