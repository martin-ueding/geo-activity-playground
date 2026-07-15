import abc
import datetime
import functools
import hashlib
import io
import itertools
import json
import logging
import pathlib
from types import SimpleNamespace
from typing import Any

import altair as alt
import geojson
import matplotlib
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
from ...core.datamodel import DB, Activity, ExplorerTileBookmark, TileVisit, UiConfig
from ...core.raster_map import OSM_TILE_SIZE, ImageTransform, TileGetter
from ...core.tiles import compute_tile, get_tile_upper_left_lat_lon
from ...explorer.garmin_img import build_garmin_img, mkgmap_available
from ...explorer.grid_file import (
    get_border_tiles,
    make_explorer_tile,
    make_grid_file_geojson,
    make_grid_file_gpx,
    make_grid_file_kml,
    make_grid_file_kml_squadrats,
    make_grid_file_osm,
    make_grid_points,
)
from ...explorer.tile_visits import (
    compute_tile_evolution,
    get_activity_ids_in_bounds,
    get_biggest_cluster_members,
    get_cluster_history_latest_event_index,
    get_cluster_id_for_tile,
    get_cluster_members,
    get_cluster_membership_in_bounds,
    get_cluster_size_history_df,
    get_cluster_state_at_cutoff,
    get_cluster_tile_count,
    get_cluster_tile_diff_for_activity,
    get_cluster_tiles_at_cutoff,
    get_explorer_square,
    get_max_cluster,
    get_square_history_df,
    get_tile_count,
    get_tile_history_df,
    get_tile_medians,
    get_tile_visits_in_bounds,
)
from ...explorer.video import ExplorerVideoOptions, generate_explorer_video
from ..authenticator import Authenticator, needs_authentication

alt.data_transformers.enable("vegafusion")

logger = logging.getLogger(__name__)


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


def blend_color(
    base: np.ndarray, addition: np.ndarray | float, opacity: float
) -> np.ndarray:
    return (1 - opacity) * base + opacity * addition


@functools.cache
def hex_color_to_float(color: str) -> np.ndarray:
    values = [int("".join(x), base=16) / 255 for x in itertools.batched(color[1:], 2)]
    assert min(values) >= 0.0 and max(values) <= 1.0, (
        f"All {values=} must be within 0.0 and 1.0."
    )
    return np.array([[values]])


class ColorStrategy(abc.ABC):
    @abc.abstractmethod
    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        pass


class MaxClusterColorStrategy(ColorStrategy):
    def __init__(
        self,
        membership: dict[tuple[int, int], tuple[int, int]],
        max_cluster_id: tuple[int, int] | None,
        tile_visits,
        config: UiConfig,
    ):
        self.membership = membership
        self.max_cluster_id = max_cluster_id
        self.tile_visits = tile_visits
        self._config = config

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        cluster_id = self.membership.get(tile_xy)
        if cluster_id is not None:
            if cluster_id == self.max_cluster_id:
                return hex_color_to_float(self._config.color_strategy_max_cluster_color)
            return hex_color_to_float(
                self._config.color_strategy_max_cluster_other_color
            )
        elif tile_xy in self.tile_visits:
            return hex_color_to_float(self._config.color_strategy_visited_color)
        else:
            return None


class ColorfulClusterColorStrategy(ColorStrategy):
    def __init__(
        self,
        membership: dict[tuple[int, int], tuple[int, int]],
        tile_visits,
        config: UiConfig,
    ):
        self.membership = membership
        self.tile_visits = tile_visits
        self._cmap = matplotlib.colormaps["hsv"]
        self._config = config

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        cluster_id = self.membership.get(tile_xy)
        if cluster_id is not None:
            m = hashlib.sha256()
            m.update(str(cluster_id).encode())
            d = int(m.hexdigest(), base=16) / (256.0**m.digest_size)
            return np.array(
                [[self._cmap(d)[:3] + (self._config.color_strategy_cmap_opacity,)]]
            )
        elif tile_xy in self.tile_visits:
            return hex_color_to_float(self._config.color_strategy_visited_color)
        else:
            return None


def _replay_root(
    parents: dict[tuple[int, int], tuple[int, int]], tile: tuple[int, int]
) -> tuple[int, int]:
    root = tile
    while parents[root] != root:
        root = parents[root]
    return root


class HistoricalColorfulClusterColorStrategy(ColorStrategy):
    def __init__(self, state, config: UiConfig):
        self._config = config
        self._cmap = matplotlib.colormaps["hsv"]
        self._color_by_tile: dict[tuple[int, int], np.ndarray] = {}
        self._visited_tiles = set(state.visited_tiles)
        for tile in state.cluster_tiles:
            cluster_id = _replay_root(state.parents, tile)
            m = hashlib.sha256()
            m.update(str(cluster_id).encode())
            d = int(m.hexdigest(), base=16) / (256.0**m.digest_size)
            self._color_by_tile[tile] = np.array(
                [[self._cmap(d)[:3] + (self._config.color_strategy_cmap_opacity,)]]
            )

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        color = self._color_by_tile.get(tile_xy)
        if color is not None:
            return color
        if tile_xy in self._visited_tiles:
            return hex_color_to_float(self._config.color_strategy_visited_color)
        return None


class HistoricalMaxClusterColorStrategy(ColorStrategy):
    def __init__(self, state, config: UiConfig):
        self._config = config
        max_root = max(
            state.component_sizes, key=state.component_sizes.get, default=None
        )
        self._max_members: set[tuple[int, int]] = set()
        if max_root is not None:
            self._max_members = {
                tile
                for tile in state.cluster_tiles
                if _replay_root(state.parents, tile) == max_root
            }
        self._cluster_tiles = set(state.cluster_tiles)
        self._visited_tiles = set(state.visited_tiles)

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        if tile_xy in self._max_members:
            return hex_color_to_float(self._config.color_strategy_max_cluster_color)
        if tile_xy in self._cluster_tiles:
            return hex_color_to_float(
                self._config.color_strategy_max_cluster_other_color
            )
        if tile_xy in self._visited_tiles:
            return hex_color_to_float(self._config.color_strategy_visited_color)
        return None


class VisitTimeColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig, use_first=True):
        self.tile_visits = tile_visits
        self.use_first = use_first
        self._config = config

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        if tile_xy in self.tile_visits:
            today = datetime.date.today()
            cmap = matplotlib.colormaps["plasma"]
            tile_info = self.tile_visits[tile_xy]
            relevant_time = (
                tile_info["first_time"] if self.use_first else tile_info["last_time"]
            )
            if pd.isna(relevant_time):
                color = hex_color_to_float(self._config.color_strategy_visited_color)
            else:
                last_age_days = (today - relevant_time.date()).days
                color = cmap(max(1 - last_age_days / (2 * 365), 0.0))
                color = np.array(
                    [[color[:3] + (self._config.color_strategy_cmap_opacity,)]]
                )
            return color
        else:
            return None


class NumVisitsColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig):
        self.tile_visits = tile_visits
        self._config = config

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        if tile_xy in self.tile_visits:
            cmap = matplotlib.colormaps["viridis"]
            tile_info = self.tile_visits[tile_xy]
            color = cmap(min(tile_info["visit_count"] / 50, 1.0))
            return np.array([[color[:3] + (self._config.color_strategy_cmap_opacity,)]])
        else:
            return None


class MissingColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig):
        self.tile_visits = tile_visits
        self._config = config

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        if tile_xy in self.tile_visits:
            return None
        else:
            return hex_color_to_float(self._config.color_strategy_visited_color)


class VisitedColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig):
        self.tile_visits = tile_visits
        self._config = config

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        if tile_xy in self.tile_visits:
            return hex_color_to_float(self._config.color_strategy_visited_color)
        else:
            return None


class SquarePlannerColorStrategy(ColorStrategy):
    def __init__(
        self,
        tile_visits,
        config: UiConfig,
        square_x: int,
        square_y: int,
        square_size: int,
    ):
        self.tile_visits = tile_visits
        self._config = config
        self.square_x = square_x
        self.square_y = square_y
        self.square_size = square_size

    def _color(self, tile_xy: tuple[int, int]) -> np.ndarray | None:
        x, y = tile_xy
        if (
            self.square_x <= x < self.square_x + self.square_size
            and self.square_y <= y < self.square_y + self.square_size
        ):
            if tile_xy in self.tile_visits:
                return hex_color_to_float("#00aa004d")
            else:
                return hex_color_to_float("#aa00004d")
        elif tile_xy in self.tile_visits:
            return hex_color_to_float(self._config.color_strategy_visited_color)
        else:
            return None


def make_explorer_blueprint(
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
    tile_getter: TileGetter,
    image_transforms: dict[str, ImageTransform],
) -> Blueprint:
    blueprint = Blueprint("explorer", __name__, template_folder="templates")

    @blueprint.route("/enable-zoom-level/<int:zoom>")
    @needs_authentication(authenticator)
    def enable_zoom_level(zoom: int) -> ResponseReturnValue:
        if 0 <= zoom <= 19:
            ui_config = config_accessor.ui()
            ui_config.explorer_zoom_levels.append(zoom)
            ui_config.explorer_zoom_levels.sort()
            config_accessor.save()
            compute_tile_evolution(ui_config)
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
        points = get_border_tiles(tiles, zoom, tile_bounds)
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

        square_x, square_y, square_size = get_explorer_square(zoom)

        # Get data from database
        medians = get_tile_medians(zoom)
        median_lat, median_lon = get_tile_upper_left_lat_lon(
            medians[0], medians[1], zoom
        )
        num_tiles = get_tile_count(zoom)
        tile_history = get_tile_history_df(zoom)

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

        biggest_cluster_members = get_biggest_cluster_members(zoom)
        _max_cluster_representative, max_cluster_size = get_max_cluster(zoom)

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
            "plot_tile_evolution": plot_tile_evolution(tile_history),
            "plot_cluster_evolution": plot_cluster_evolution(
                get_cluster_size_history_df(zoom)
            ),
            "plot_square_evolution": plot_square_evolution(get_square_history_df(zoom)),
            "zoom": zoom,
            "num_tiles": num_tiles,
            "num_cluster_tiles": get_cluster_tile_count(zoom),
            "square_x": square_x,
            "square_y": square_y,
            "square_size": square_size,
            "max_cluster_size": max_cluster_size,
            "bookmarks": bookmarks,
            "mkgmap_available": mkgmap_available(),
        }
        return render_template("explorer/server-side.html.j2", **context)

    @blueprint.route("/video")
    @needs_authentication(authenticator)
    def video() -> ResponseReturnValue:
        zoom_levels = sorted(set(config_accessor.ui().explorer_zoom_levels))
        selected_zoom = request.args.get("zoom", type=int)
        if selected_zoom not in zoom_levels:
            selected_zoom = zoom_levels[0] if zoom_levels else 14
        return render_template(
            "explorer/video.html.j2",
            zoom_levels=zoom_levels,
            selected_zoom=selected_zoom,
        )

    @blueprint.post("/video")
    @needs_authentication(authenticator)
    def generate_video() -> ResponseReturnValue:
        zoom = request.form.get("zoom", type=int, default=14)
        if zoom not in config_accessor.ui().explorer_zoom_levels:
            flash(_("The selected zoom level is not enabled."), category="danger")
            return redirect(url_for(".video"))
        video_width = request.form.get("video_width", type=int, default=1920)
        video_height = request.form.get("video_height", type=int, default=1080)
        fps = request.form.get("fps", type=int, default=30)
        steps_per_tile = request.form.get("steps_per_tile", type=int, default=12)
        fade_frames = request.form.get("fade_frames", type=int, default=12)
        download_workers = request.form.get("download_workers", type=int, default=16)

        if video_width <= 0 or video_height <= 0 or fps <= 0:
            flash(_("Width, height and FPS must be positive."), category="danger")
            return redirect(url_for(".video", zoom=zoom))
        if steps_per_tile <= 0 or fade_frames < 0:
            flash(
                _(
                    "Steps per tile must be positive and fade frames must be non-negative."
                ),
                category="danger",
            )
            return redirect(url_for(".video", zoom=zoom))
        if download_workers <= 0:
            flash(_("Download workers must be positive."), category="danger")
            return redirect(url_for(".video", zoom=zoom))

        try:
            output_path = generate_explorer_video(
                ExplorerVideoOptions(
                    basedir=pathlib.Path.cwd(),
                    zoom=zoom,
                    width=video_width,
                    height=video_height,
                    fps=fps,
                    steps_per_tile=steps_per_tile,
                    fade_frames=fade_frames,
                    download_workers=download_workers,
                )
            )
        except Exception as exc:
            logger.exception("Failed to generate explorer video")
            flash(
                _("Could not generate explorer video: %(error)s", error=str(exc)),
                category="danger",
            )
        else:
            flash(
                _("Explorer video written to %(path)s", path=str(output_path)),
                category="success",
            )
        return redirect(url_for(".video", zoom=zoom))

    @blueprint.after_request
    def add_cors_headers(response: Response) -> Response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @blueprint.route("/<int:zoom>/style.json")
    def style_json(zoom: int) -> ResponseReturnValue:
        color_strategy = request.args.get("color_strategy", "colorful_cluster")
        base_url = request.url_root.rstrip("/")
        tile_url = (
            f"{base_url}/explorer/{zoom}/tile/{{z}}/{{x}}/{{y}}.png"
            f"?color_strategy={color_strategy}"
        )
        gap_source_id = f"gap-explorer-{zoom}-{color_strategy}"
        gap_source = {
            "type": "raster",
            "tiles": [tile_url],
            "tileSize": 256,
        }
        gap_layer = {
            "id": f"gap-explorer-layer-{zoom}-{color_strategy}",
            "type": "raster",
            "source": gap_source_id,
            "paint": {"raster-opacity": 0.8},
        }

        map_style_url = config_accessor.map().map_style_url
        if map_style_url:
            style = requests.get(map_style_url, timeout=10).json()
            style["sources"][gap_source_id] = gap_source
            style["layers"].append(gap_layer)
        else:
            raster_tile_url = config_accessor.map().map_tile_url.replace(
                "{zoom}", "{z}"
            )
            style = {
                "version": 8,
                "sources": {
                    "base-map": {
                        "type": "raster",
                        "tiles": [raster_tile_url],
                        "tileSize": 256,
                    },
                    gap_source_id: gap_source,
                },
                "layers": [
                    {"id": "base-map-layer", "type": "raster", "source": "base-map"},
                    gap_layer,
                ],
            }

        return Response(json.dumps(style), mimetype="application/json")

    @blueprint.route("/<int:zoom>/tile/<int:z>/<int:x>/<int:y>.png")
    def tile(zoom: int, z: int, x: int, y: int) -> ResponseReturnValue:
        config = config_accessor.ui()
        square_x, square_y, square_size = get_explorer_square(zoom)
        evolution_state = SimpleNamespace(
            square_x=square_x, square_y=square_y, max_square_size=square_size
        )
        history_event_index = request.args.get("event_index", type=int)
        historical_state = None
        if history_event_index is not None:
            history_event_index = max(
                0,
                min(history_event_index, get_cluster_history_latest_event_index(zoom)),
            )
            historical_state = get_cluster_state_at_cutoff(zoom, history_event_index)

        # Bounding box of explorer tiles covered by this map tile, used to fetch
        # only the tile visits and cluster membership in view from the database.
        if z >= zoom:
            cover_factor = 2 ** (z - zoom)
            tx_min = tx_max = x // cover_factor
            ty_min = ty_max = y // cover_factor
        else:
            cover_factor = 2 ** (zoom - z)
            tx_min, tx_max = x * cover_factor, x * cover_factor + cover_factor - 1
            ty_min, ty_max = y * cover_factor, y * cover_factor + cover_factor - 1

        tile_visits = get_tile_visits_in_bounds(zoom, tx_min, tx_max, ty_min, ty_max)

        # map_tile = np.array(tile_getter.get_tile(z, x, y)) / 255
        # grayscale = image_transforms["grayscale"].transform_image(map_tile)
        grayscale = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE, 4), dtype=np.float32)
        square_line_width = 3
        square_color = np.array([[[228, 26, 28, 255]]]) / 256

        color_strategy_name = request.args.get("color_strategy", "colorful_cluster")
        if color_strategy_name == "default":
            color_strategy_name = config_accessor.ui().cluster_color_strategy
        match color_strategy_name:
            case "max_cluster":
                if historical_state is None:
                    membership = get_cluster_membership_in_bounds(
                        zoom, tx_min, tx_max, ty_min, ty_max
                    )
                    max_cluster_id, _ = get_max_cluster(zoom)
                    color_strategy = MaxClusterColorStrategy(
                        membership, max_cluster_id, tile_visits, config
                    )
                else:
                    color_strategy = HistoricalMaxClusterColorStrategy(
                        historical_state, config
                    )
            case "colorful_cluster":
                if historical_state is None:
                    membership = get_cluster_membership_in_bounds(
                        zoom, tx_min, tx_max, ty_min, ty_max
                    )
                    color_strategy = ColorfulClusterColorStrategy(
                        membership, tile_visits, config
                    )
                else:
                    color_strategy = HistoricalColorfulClusterColorStrategy(
                        historical_state, config
                    )
            case "first":
                color_strategy = VisitTimeColorStrategy(
                    tile_visits, config, use_first=True
                )
            case "last":
                color_strategy = VisitTimeColorStrategy(
                    tile_visits, config, use_first=False
                )
            case "visits":
                color_strategy = NumVisitsColorStrategy(tile_visits, config)
            case "missing":
                color_strategy = MissingColorStrategy(tile_visits, config)
            case "visited":
                color_strategy = VisitedColorStrategy(tile_visits, config)
            case "square_planner":
                color_strategy = SquarePlannerColorStrategy(
                    tile_visits,
                    config,
                    int(request.args["x"]),
                    int(request.args["y"]),
                    int(request.args["size"]),
                )
            case _:
                raise ValueError("Unsupported color strategy.")

        if z >= zoom:
            factor = 2 ** (z - zoom)
            tile_x = x // factor
            tile_y = y // factor
            tile_xy = (tile_x, tile_y)
            color = color_strategy._color(tile_xy)
            if color is None:
                result = grayscale
            else:
                result = np.broadcast_to(color, grayscale.shape).copy()

            if x % factor == 0:
                result[:, 0, :] = 0.5
            if y % factor == 0:
                result[0, :, :] = 0.5

            if (
                evolution_state.square_x is not None
                and evolution_state.square_y is not None
            ):
                if (
                    x % factor == 0
                    and tile_x == evolution_state.square_x
                    and evolution_state.square_y
                    <= tile_y
                    < evolution_state.square_y + evolution_state.max_square_size
                ):
                    result[:, 0:square_line_width] = square_color
                if (
                    y % factor == 0
                    and tile_y == evolution_state.square_y
                    and evolution_state.square_x
                    <= tile_x
                    < evolution_state.square_x + evolution_state.max_square_size
                ):
                    result[0:square_line_width, :] = square_color
                if (
                    (x + 1) % factor == 0
                    and (x + 1) // factor
                    == evolution_state.square_x + evolution_state.max_square_size
                    and evolution_state.square_y
                    <= tile_y
                    < evolution_state.square_y + evolution_state.max_square_size
                ):
                    result[:, -square_line_width:] = square_color
                if (
                    (y + 1) % factor == 0
                    and (y + 1) // factor
                    == evolution_state.square_y + evolution_state.max_square_size
                    and evolution_state.square_x
                    <= tile_x
                    < evolution_state.square_x + evolution_state.max_square_size
                ):
                    result[-square_line_width:, :] = square_color
        else:
            result = grayscale
            factor = 2 ** (zoom - z)
            width = 256 // factor
            for xo in range(factor):
                for yo in range(factor):
                    tile_x = x * factor + xo
                    tile_y = y * factor + yo
                    tile_xy = (tile_x, tile_y)
                    color = color_strategy._color(tile_xy)
                    if color is not None:
                        result[
                            yo * width : (yo + 1) * width, xo * width : (xo + 1) * width
                        ] = color

                    if (
                        evolution_state.square_x is not None
                        and evolution_state.square_y is not None
                    ):
                        if (
                            tile_x == evolution_state.square_x
                            and evolution_state.square_y
                            <= tile_y
                            < evolution_state.square_y + evolution_state.max_square_size
                        ):
                            result[
                                yo * width : (yo + 1) * width,
                                xo * width : xo * width + square_line_width,
                            ] = square_color
                        if (
                            tile_y == evolution_state.square_y
                            and evolution_state.square_x
                            <= tile_x
                            < evolution_state.square_x + evolution_state.max_square_size
                        ):
                            result[
                                yo * width : yo * width + square_line_width,
                                xo * width : (xo + 1) * width,
                            ] = square_color

                        if (
                            tile_x + 1
                            == evolution_state.square_x
                            + evolution_state.max_square_size
                            and evolution_state.square_y
                            <= tile_y
                            < evolution_state.square_y + evolution_state.max_square_size
                        ):
                            result[
                                yo * width : (yo + 1) * width,
                                (xo + 1) * width - square_line_width : (xo + 1) * width,
                            ] = square_color

                        if (
                            tile_y + 1
                            == evolution_state.square_y
                            + evolution_state.max_square_size
                            and evolution_state.square_x
                            <= tile_x
                            < evolution_state.square_x + evolution_state.max_square_size
                        ):
                            result[
                                (yo + 1) * width - square_line_width : (yo + 1) * width,
                                xo * width : (xo + 1) * width,
                            ] = square_color
                    if width >= 64:
                        result[yo * width, :, :] = 0.5
                        result[:, xo * width, :] = 0.5
        f = io.BytesIO()
        pl.imsave(f, result, format="png")
        return Response(
            bytes(f.getbuffer()),
            mimetype="image/png",
            headers={"Cache-Control": "no-cache"},
        )

    @blueprint.route(
        "/<int:zoom>/info/<float(signed=True):latitude>/<float(signed=True):longitude>"
    )
    def info(zoom: int, latitude: float, longitude: float) -> str:
        _square_x, _square_y, square_size = get_explorer_square(zoom)
        tile_xy = compute_tile(latitude, longitude, zoom)
        cluster_id = get_cluster_id_for_tile(zoom, tile_xy[0], tile_xy[1])
        context: dict[str, Any] = {
            "tile_x": tile_xy[0],
            "tile_y": tile_xy[1],
            "zoom": zoom,
            "square_size": square_size,
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
        added, removed = get_cluster_tile_diff_for_activity(zoom, activity_id)
        features = [
            make_explorer_tile(
                tile_x=tile_x,
                tile_y=tile_y,
                properties={"delta": "added"},
                zoom=zoom,
            )
            for tile_x, tile_y in sorted(added)
        ] + [
            make_explorer_tile(
                tile_x=tile_x,
                tile_y=tile_y,
                properties={"delta": "removed"},
                zoom=zoom,
            )
            for tile_x, tile_y in sorted(removed)
        ]
        return Response(
            geojson.dumps(geojson.FeatureCollection(features)),
            mimetype="application/json",
        )

    return blueprint


def geojson_bounding_box_for_tile_collection(
    tiles: list[tuple[int, int]], zoom: int
) -> str:
    min_x = min(x for x, y in tiles)
    max_x = max(x for x, y in tiles)
    min_y = min(y for x, y in tiles)
    max_y = max(y for x, y in tiles)
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
        alt.Chart(tiles, title=_("Tiles"))
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Time")), alt.Y("count", title=_("Number of tiles"))
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def plot_cluster_evolution(cluster_evolution: pd.DataFrame) -> str:
    if len(cluster_evolution) == 0:
        return ""
    return (
        alt.Chart(cluster_evolution, title=_("Cluster"))
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("max_cluster_size", title=_("Maximum cluster size")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def plot_square_evolution(square_evolution: pd.DataFrame) -> str:
    if len(square_evolution) == 0:
        return ""
    return (
        alt.Chart(square_evolution, title=_("Square"))
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Time")),
            alt.Y("max_square_size", title=_("Maximum square size")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )
