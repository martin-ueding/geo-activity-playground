import abc
import datetime
import functools
import hashlib
import itertools
from types import SimpleNamespace
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

from ...core.coordinates import Bounds
from ...core.datamodel import UiConfig
from ...core.raster_map import OSM_TILE_SIZE
from ...core.tile_visits import get_latest_new_tiles_activity_id
from .clustering import (
    get_cluster_membership_in_bounds,
    get_max_cluster,
)

SQUARE_LINE_WIDTH = 3
SQUARE_COLOR = np.array([228, 26, 28, 255], dtype=np.float32) / 256.0
GRID_COLOR = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)

INACCESSIBLE_STRIPE_COLOR = np.array([0.5, 0.5, 0.5, 0.6], dtype=np.float32)
INACCESSIBLE_STRIPE_PERIOD = 16
INACCESSIBLE_STRIPE_THICKNESS = 8


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
    return np.array([[values]], dtype=np.float32)


class TilePattern(abc.ABC):
    @abc.abstractmethod
    def rasterize(self, shape: tuple[int, int]) -> np.ndarray:
        """Return a (height, width, 4) float32 RGBA array."""


class SolidColor(TilePattern):
    def __init__(self, color: np.ndarray | list[float] | tuple[float, ...]) -> None:
        self._color = np.asarray(color, dtype=np.float32)

    def rasterize(self, shape: tuple[int, int]) -> np.ndarray:
        height, width = shape
        return np.broadcast_to(self._color, (height, width, 4)).copy()


class HatchedPattern(TilePattern):
    def __init__(self, color: np.ndarray, period: int, thickness: int) -> None:
        self._color = np.asarray(color, dtype=np.float32)
        self._period = period
        self._thickness = thickness

    def rasterize(self, shape: tuple[int, int]) -> np.ndarray:
        height, width = shape
        rgba = np.zeros((height, width, 4), dtype=np.float32)
        mask = np.fromfunction(
            lambda i, j: (i + j) % self._period < self._thickness,
            (height, width),
            dtype=int,
        )
        rgba[mask] = self._color
        return rgba


def alpha_composite(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    """Composite a RGBA overlay onto a RGBA base image."""
    a = overlay[..., 3]
    out = np.copy(base)
    out[..., :3] = (1 - a[..., np.newaxis]) * base[..., :3] + a[
        ..., np.newaxis
    ] * overlay[..., :3]
    out[..., 3] = base[..., 3] + (1 - base[..., 3]) * a
    return out


HATCHED_PATTERN = HatchedPattern(
    INACCESSIBLE_STRIPE_COLOR,
    INACCESSIBLE_STRIPE_PERIOD,
    INACCESSIBLE_STRIPE_THICKNESS,
)


class ColorStrategy(abc.ABC):
    @abc.abstractmethod
    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None: ...


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

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        cluster_id = self.membership.get(tile_xy)
        if cluster_id is not None:
            if cluster_id == self.max_cluster_id:
                return SolidColor(
                    hex_color_to_float(self._config.color_strategy_max_cluster_color)
                )
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_max_cluster_other_color)
            )
        elif tile_xy in self.tile_visits:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
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

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        cluster_id = self.membership.get(tile_xy)
        if cluster_id is not None:
            m = hashlib.sha256()
            m.update(str(cluster_id).encode())
            d = int(m.hexdigest(), base=16) / (256.0**m.digest_size)
            return SolidColor(
                self._cmap(d)[:3] + (self._config.color_strategy_cmap_opacity,)
            )
        elif tile_xy in self.tile_visits:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
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
        self._color_by_tile: dict[tuple[int, int], TilePattern] = {}
        self._visited_tiles = set(state.visited_tiles)
        for tile in state.cluster_tiles:
            cluster_id = _replay_root(state.parents, tile)
            m = hashlib.sha256()
            m.update(str(cluster_id).encode())
            d = int(m.hexdigest(), base=16) / (256.0**m.digest_size)
            self._color_by_tile[tile] = SolidColor(
                self._cmap(d)[:3] + (self._config.color_strategy_cmap_opacity,)
            )

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        color = self._color_by_tile.get(tile_xy)
        if color is not None:
            return color
        if tile_xy in self._visited_tiles:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
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

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self._max_members:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_max_cluster_color)
            )
        if tile_xy in self._cluster_tiles:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_max_cluster_other_color)
            )
        if tile_xy in self._visited_tiles:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
        return None


class VisitTimeColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig, use_first=True):
        self.tile_visits = tile_visits
        self.use_first = use_first
        self._config = config

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
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
                color = color[:3] + (self._config.color_strategy_cmap_opacity,)
            return SolidColor(color)
        else:
            return None


class NumVisitsColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig):
        self.tile_visits = tile_visits
        self._config = config

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self.tile_visits:
            cmap = matplotlib.colormaps["viridis"]
            tile_info = self.tile_visits[tile_xy]
            color = cmap(min(tile_info["visit_count"] / 50, 1.0))
            return SolidColor(color[:3] + (self._config.color_strategy_cmap_opacity,))
        else:
            return None


class MissingColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig):
        self.tile_visits = tile_visits
        self._config = config

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self.tile_visits:
            return None
        else:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )


class VisitedColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig):
        self.tile_visits = tile_visits
        self._config = config

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self.tile_visits:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
        else:
            return None


class LatestNewTilesColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, config: UiConfig, latest_activity_id: int | None):
        self.tile_visits = tile_visits
        self._config = config
        self._latest_activity_id = latest_activity_id

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        info = self.tile_visits.get(tile_xy)
        if info is not None and info["first_id"] == self._latest_activity_id:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
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

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        x, y = tile_xy
        if (
            self.square_x <= x < self.square_x + self.square_size
            and self.square_y <= y < self.square_y + self.square_size
        ):
            if tile_xy in self.tile_visits:
                return SolidColor(hex_color_to_float("#00aa004d"))
            else:
                return SolidColor(hex_color_to_float("#aa00004d"))
        elif tile_xy in self.tile_visits:
            return SolidColor(
                hex_color_to_float(self._config.color_strategy_visited_color)
            )
        else:
            return None


def _tile_bounds(zoom: int, z: int, x: int, y: int) -> Bounds:
    if z >= zoom:
        factor = 2 ** (z - zoom)
        tx_min = tx_max = x // factor
        ty_min = ty_max = y // factor
    else:
        factor = 2 ** (zoom - z)
        tx_min, tx_max = x * factor, x * factor + factor - 1
        ty_min, ty_max = y * factor, y * factor + factor - 1
    return Bounds(tx_min, ty_min, tx_max, ty_max)


def _resolve_color_strategy(
    request: Any,
    zoom: int,
    tile_visits: dict[tuple[int, int], Any],
    tx_min: int,
    tx_max: int,
    ty_min: int,
    ty_max: int,
    historical_state: Any | None,
    config: UiConfig,
) -> ColorStrategy:
    color_strategy_name = request.args.get("color_strategy", "colorful_cluster")
    if color_strategy_name == "default":
        color_strategy_name = config.cluster_color_strategy
    match color_strategy_name:
        case "max_cluster":
            if historical_state is None:
                membership = get_cluster_membership_in_bounds(
                    zoom, tx_min, tx_max, ty_min, ty_max
                )
                max_cluster_id, _ = get_max_cluster(zoom)
                return MaxClusterColorStrategy(
                    membership, max_cluster_id, tile_visits, config
                )
            else:
                return HistoricalMaxClusterColorStrategy(historical_state, config)
        case "colorful_cluster":
            if historical_state is None:
                membership = get_cluster_membership_in_bounds(
                    zoom, tx_min, tx_max, ty_min, ty_max
                )
                return ColorfulClusterColorStrategy(membership, tile_visits, config)
            else:
                return HistoricalColorfulClusterColorStrategy(historical_state, config)
        case "first":
            return VisitTimeColorStrategy(tile_visits, config, use_first=True)
        case "last":
            return VisitTimeColorStrategy(tile_visits, config, use_first=False)
        case "visits":
            return NumVisitsColorStrategy(tile_visits, config)
        case "missing":
            return MissingColorStrategy(tile_visits, config)
        case "visited":
            return VisitedColorStrategy(tile_visits, config)
        case "latest_new":
            return LatestNewTilesColorStrategy(
                tile_visits, config, get_latest_new_tiles_activity_id(zoom)
            )
        case "square_planner":
            return SquarePlannerColorStrategy(
                tile_visits,
                config,
                int(request.args["x"]),
                int(request.args["y"]),
                int(request.args["size"]),
            )
        case _:
            raise ValueError("Unsupported color strategy.")


def _draw_grid_lines(
    result: np.ndarray,
    x_start: int,
    y_start: int,
    width: int,
    draw_left: bool,
    draw_top: bool,
) -> None:
    if draw_left and width >= 64:
        result[:, x_start, :] = GRID_COLOR
    if draw_top and width >= 64:
        result[y_start, :, :] = GRID_COLOR


def _draw_explorer_square_edges(
    result: np.ndarray,
    x_start: int,
    y_start: int,
    width: int,
    tile_x: int,
    tile_y: int,
    evolution_state: SimpleNamespace,
    draw_left: bool,
    draw_top: bool,
    draw_right: bool,
    draw_bottom: bool,
) -> None:
    square_x = evolution_state.square_x
    square_y = evolution_state.square_y
    square_size = evolution_state.max_square_size
    if square_x is None or square_y is None or square_size <= 0:
        return

    in_square_y = square_y <= tile_y < square_y + square_size
    in_square_x = square_x <= tile_x < square_x + square_size

    if in_square_y and draw_left and tile_x == square_x:
        result[y_start : y_start + width, x_start : x_start + SQUARE_LINE_WIDTH] = (
            SQUARE_COLOR
        )
    if in_square_x and draw_top and tile_y == square_y:
        result[y_start : y_start + SQUARE_LINE_WIDTH, x_start : x_start + width] = (
            SQUARE_COLOR
        )
    if in_square_y and draw_right and tile_x + 1 == square_x + square_size:
        result[
            y_start : y_start + width,
            x_start + width - SQUARE_LINE_WIDTH : x_start + width,
        ] = SQUARE_COLOR
    if in_square_x and draw_bottom and tile_y + 1 == square_y + square_size:
        result[
            y_start + width - SQUARE_LINE_WIDTH : y_start + width,
            x_start : x_start + width,
        ] = SQUARE_COLOR


def _render_tile_image(
    zoom: int,
    z: int,
    x: int,
    y: int,
    color_strategy: ColorStrategy,
    evolution_state: SimpleNamespace,
    inaccessible_tiles: frozenset[tuple[int, int]] | None = None,
) -> np.ndarray:
    if inaccessible_tiles is None:
        inaccessible_tiles = frozenset()
    result = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE, 4), dtype=np.float32)

    if z >= zoom:
        factor = 2 ** (z - zoom)
        tile_x = x // factor
        tile_y = y // factor
        subtiles = [
            (
                tile_x,
                tile_y,
                0,
                0,
                OSM_TILE_SIZE,
                x % factor == 0,
                y % factor == 0,
                (x + 1) % factor == 0,
                (y + 1) % factor == 0,
            )
        ]
    else:
        factor = 2 ** (zoom - z)
        width = OSM_TILE_SIZE // factor
        subtiles = [
            (
                x * factor + xo,
                y * factor + yo,
                xo * width,
                yo * width,
                width,
                True,
                True,
                True,
                True,
            )
            for xo in range(factor)
            for yo in range(factor)
        ]

    for (
        tile_x,
        tile_y,
        x_start,
        y_start,
        width,
        draw_left,
        draw_top,
        draw_right,
        draw_bottom,
    ) in subtiles:
        tile_xy = (tile_x, tile_y)
        pattern = color_strategy.color(tile_xy)
        if pattern is not None:
            result[
                y_start : y_start + width,
                x_start : x_start + width,
            ] = pattern.rasterize((width, width))

        if tile_xy in inaccessible_tiles:
            hatch = HATCHED_PATTERN.rasterize((width, width))
            result[
                y_start : y_start + width,
                x_start : x_start + width,
            ] = alpha_composite(
                result[y_start : y_start + width, x_start : x_start + width],
                hatch,
            )

        _draw_grid_lines(result, x_start, y_start, width, draw_left, draw_top)
        _draw_explorer_square_edges(
            result,
            x_start,
            y_start,
            width,
            tile_x,
            tile_y,
            evolution_state,
            draw_left,
            draw_top,
            draw_right,
            draw_bottom,
        )

    return result
