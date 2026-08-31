import abc
import dataclasses
import datetime
import functools
import hashlib
import itertools
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from types import SimpleNamespace
from typing import Any, NamedTuple

import matplotlib
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from ...core.coordinates import Bounds
from ...core.datamodel import UiConfig
from ...core.raster_map import OSM_TILE_SIZE
from ...core.tile_visits import (
    get_first_visits_for_activity,
    get_latest_new_tiles_day,
    get_new_tiles_activity_ids_on_day,
    get_new_tiles_on_day,
)
from .clustering import (
    get_cluster_history_cutoff_for_activity,
    get_cluster_history_latest_event_index,
    get_cluster_membership_in_bounds,
    get_cluster_tiles_at_cutoff,
    get_cluster_tiles_gained_by_activity,
    get_max_cluster,
)
from .model import BorderStroke, TileStyle, TileStyleName, get_tile_styles

SQUARE_LINE_WIDTH = 3
SQUARE_COLOR = np.array([228, 26, 28, 255], dtype=np.float32) / 256.0

STRIPES_PER_TILE = 8
DASHES_PER_TILE_EDGE = 8


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


def _over(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Alpha-composite ``source`` over ``target``, both straight-alpha RGBA."""
    source_alpha = source[..., 3:4]
    target_alpha = target[..., 3:4]
    out_alpha = source_alpha + target_alpha * (1 - source_alpha)
    out_rgb = np.divide(
        source[..., :3] * source_alpha
        + target[..., :3] * target_alpha * (1 - source_alpha),
        out_alpha,
        out=np.zeros_like(source[..., :3]),
        where=out_alpha > 0,
    )
    return np.concatenate([out_rgb, out_alpha], axis=-1)


@dataclasses.dataclass(frozen=True)
class TileStyleSpec:
    """Immutable, hashable snapshot of a :class:`TileStyle` row."""

    fill_color: tuple[float, float, float, float]
    border_color: tuple[float, float, float, float]
    border_width: int
    border_dashed: bool
    stripe_color: tuple[float, float, float, float]

    @classmethod
    def from_model(cls, style: TileStyle) -> "TileStyleSpec":
        return cls(
            fill_color=hex_color_to_tuple(style.fill_color),
            border_color=hex_color_to_tuple(style.border_color),
            border_width=style.border_width,
            border_dashed=style.border_stroke == BorderStroke.DASHED,
            stripe_color=hex_color_to_tuple(style.stripe_color),
        )


@functools.cache
def hex_color_to_tuple(color: str) -> tuple[float, float, float, float]:
    values = tuple(hex_color_to_float(color).reshape(4).tolist())
    return values  # type: ignore[return-value]


def _stripe_mask(width: int) -> np.ndarray:
    """Diagonal stripes with a fixed count per tile, so zooming keeps them."""
    period = 2 * width / STRIPES_PER_TILE
    i, j = np.indices((width, width), dtype=np.float32)
    return ((i + j) % period) < period / 2


def _border_mask(width: int, inset: int, thickness: int, dashed: bool) -> np.ndarray:
    mask = np.zeros((width, width), dtype=bool)
    span = slice(inset, width - inset)
    if dashed:
        period = max(2.0, width / DASHES_PER_TILE_EDGE)
        along = (np.arange(width, dtype=np.float32) % period) < period / 2
    else:
        along = np.ones(width, dtype=bool)
    mask[inset : inset + thickness, span] = along[np.newaxis, span]
    mask[width - inset - thickness : width - inset, span] = along[np.newaxis, span]
    mask[span, inset : inset + thickness] = along[span, np.newaxis]
    mask[span, width - inset - thickness : width - inset] = along[span, np.newaxis]
    return mask


@functools.lru_cache(maxsize=256)
def _rasterize_spec(spec: TileStyleSpec, width: int) -> np.ndarray:
    """Render fill, stripes and border of one style.

    The result is shared between all tiles with the same style, so callers must
    treat it as read-only.
    """
    rgba = np.zeros((width, width, 4), dtype=np.float32)

    if spec.fill_color[3] > 0:
        fill = np.broadcast_to(
            np.array(spec.fill_color, dtype=np.float32), (width, width, 4)
        )
        rgba = _over(fill, rgba)

    if spec.stripe_color[3] > 0:
        layer = np.zeros((width, width, 4), dtype=np.float32)
        layer[_stripe_mask(width)] = spec.stripe_color
        rgba = _over(layer, rgba)

    if spec.border_color[3] > 0 and spec.border_width > 0:
        thickness = min(max(1, round(spec.border_width * width / OSM_TILE_SIZE)), width)
        layer = np.zeros((width, width, 4), dtype=np.float32)
        layer[_border_mask(width, 0, thickness, spec.border_dashed)] = spec.border_color
        rgba = _over(layer, rgba)

    return rgba


class StyledTilePattern(TilePattern):
    def __init__(self, spec: TileStyleSpec | None) -> None:
        self._spec = spec

    def __bool__(self) -> bool:
        return self._spec is not None

    def rasterize(self, shape: tuple[int, int]) -> np.ndarray:
        _, width = shape
        assert self._spec is not None
        return _rasterize_spec(self._spec, width)


PREVIEW_CHECKER_SIZE = 16


def render_tile_style_preview(
    spec: TileStyleSpec, width: int = OSM_TILE_SIZE
) -> np.ndarray:
    """Draw a style onto a checkerboard so that transparency stays visible."""
    i, j = np.indices((width, width))
    shade = np.where(
        (i // PREVIEW_CHECKER_SIZE + j // PREVIEW_CHECKER_SIZE) % 2 == 0, 0.95, 0.8
    ).astype(np.float32)
    background = np.ones((width, width, 4), dtype=np.float32)
    background[..., :3] = shade[..., np.newaxis]
    return _over(StyledTilePattern(spec).rasterize((width, width)), background)


def get_tile_style_specs() -> dict[TileStyleName, TileStyleSpec]:
    return {
        name: TileStyleSpec.from_model(style)
        for name, style in get_tile_styles().items()
    }


type TileStyleSpecs = dict[TileStyleName, TileStyleSpec]


class ColorStrategy(abc.ABC):
    @abc.abstractmethod
    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None: ...


def _styled(styles: TileStyleSpecs, name: TileStyleName) -> TilePattern:
    return StyledTilePattern(styles[name])


class MaxClusterColorStrategy(ColorStrategy):
    def __init__(
        self,
        membership: dict[tuple[int, int], tuple[int, int]],
        max_cluster_id: tuple[int, int] | None,
        tile_visits,
        styles: TileStyleSpecs,
    ):
        self.membership = membership
        self.max_cluster_id = max_cluster_id
        self.tile_visits = tile_visits
        self._styles = styles

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        cluster_id = self.membership.get(tile_xy)
        if cluster_id is not None:
            if cluster_id == self.max_cluster_id:
                return _styled(self._styles, TileStyleName.MAX_CLUSTER)
            return _styled(self._styles, TileStyleName.OTHER_CLUSTER)
        elif tile_xy in self.tile_visits:
            return _styled(self._styles, TileStyleName.VISITED)
        else:
            return None


class ColorfulClusterColorStrategy(ColorStrategy):
    def __init__(
        self,
        membership: dict[tuple[int, int], tuple[int, int]],
        tile_visits,
        config: UiConfig,
        styles: TileStyleSpecs,
    ):
        self.membership = membership
        self.tile_visits = tile_visits
        self._cmap = matplotlib.colormaps["hsv"]
        self._config = config
        self._styles = styles

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        cluster_id = self.membership.get(tile_xy)
        if cluster_id is not None:
            return SolidColor(
                _cluster_cmap_color(
                    self._cmap, cluster_id, self._config.color_strategy_cmap_opacity
                )
            )
        elif tile_xy in self.tile_visits:
            return _styled(self._styles, TileStyleName.VISITED)
        else:
            return None


def _cluster_cmap_color(cmap, cluster_id: tuple[int, int], opacity: float) -> tuple:
    m = hashlib.sha256()
    m.update(str(cluster_id).encode())
    d = int(m.hexdigest(), base=16) / (256.0**m.digest_size)
    return cmap(d)[:3] + (opacity,)


def _replay_root(
    parents: dict[tuple[int, int], tuple[int, int]], tile: tuple[int, int]
) -> tuple[int, int]:
    root = tile
    while parents[root] != root:
        root = parents[root]
    return root


class HistoricalColorfulClusterColorStrategy(ColorStrategy):
    def __init__(self, state, config: UiConfig, styles: TileStyleSpecs):
        self._styles = styles
        cmap = matplotlib.colormaps["hsv"]
        self._color_by_tile: dict[tuple[int, int], TilePattern] = {}
        self._visited_tiles = set(state.visited_tiles)
        for tile in state.cluster_tiles:
            self._color_by_tile[tile] = SolidColor(
                _cluster_cmap_color(
                    cmap,
                    _replay_root(state.parents, tile),
                    config.color_strategy_cmap_opacity,
                )
            )

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        color = self._color_by_tile.get(tile_xy)
        if color is not None:
            return color
        if tile_xy in self._visited_tiles:
            return _styled(self._styles, TileStyleName.VISITED)
        return None


class HistoricalMaxClusterColorStrategy(ColorStrategy):
    def __init__(self, state, styles: TileStyleSpecs):
        self._styles = styles
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
            return _styled(self._styles, TileStyleName.MAX_CLUSTER)
        if tile_xy in self._cluster_tiles:
            return _styled(self._styles, TileStyleName.OTHER_CLUSTER)
        if tile_xy in self._visited_tiles:
            return _styled(self._styles, TileStyleName.VISITED)
        return None


class VisitTimeColorStrategy(ColorStrategy):
    def __init__(
        self, tile_visits, config: UiConfig, styles: TileStyleSpecs, use_first=True
    ):
        self.tile_visits = tile_visits
        self.use_first = use_first
        self._config = config
        self._styles = styles

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self.tile_visits:
            today = datetime.date.today()
            cmap = matplotlib.colormaps["plasma"]
            tile_info = self.tile_visits[tile_xy]
            relevant_time = (
                tile_info["first_time"] if self.use_first else tile_info["last_time"]
            )
            if pd.isna(relevant_time):
                return _styled(self._styles, TileStyleName.VISITED)
            last_age_days = (today - relevant_time.date()).days
            color = cmap(max(1 - last_age_days / (2 * 365), 0.0))
            return SolidColor(color[:3] + (self._config.color_strategy_cmap_opacity,))
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
    def __init__(
        self,
        tile_visits,
        styles: TileStyleSpecs,
        inaccessible_tiles: AbstractSet[tuple[int, int]] = frozenset(),
    ):
        self.tile_visits = tile_visits
        self._styles = styles
        self._inaccessible_tiles = inaccessible_tiles

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self.tile_visits or tile_xy in self._inaccessible_tiles:
            return None
        else:
            return _styled(self._styles, TileStyleName.MISSING)


class VisitedColorStrategy(ColorStrategy):
    def __init__(self, tile_visits, styles: TileStyleSpecs):
        self.tile_visits = tile_visits
        self._styles = styles

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        if tile_xy in self.tile_visits:
            return _styled(self._styles, TileStyleName.VISITED)
        else:
            return None


class ActivityHighlightColorStrategy(ColorStrategy):
    """Standalone layer: cluster context plus what one activity changed.

    Every tile falls into exactly one of five states, each its own style:
    already part of a cluster before the activity (``OLD_CLUSTER``), visited
    before but not clustered (``VISITED``), newly clustered by this activity
    while already visited (``VISITED_NEW_CLUSTER``), newly discovered by this
    activity without joining a cluster (``NEW_TILE``), or newly discovered and
    newly clustered in the same activity (``NEW_TILE_NEW_CLUSTER``).
    """

    def __init__(
        self,
        new_tiles: AbstractSet[tuple[int, int]],
        cluster_gained: AbstractSet[tuple[int, int]],
        old_cluster_tiles: AbstractSet[tuple[int, int]],
        tile_visits,
        styles: TileStyleSpecs,
    ):
        self._new_tiles = new_tiles
        self._cluster_gained = cluster_gained
        self._old_cluster_tiles = old_cluster_tiles
        self.tile_visits = tile_visits
        self._styles = styles

    def color(self, tile_xy: tuple[int, int]) -> TilePattern | None:
        is_new = tile_xy in self._new_tiles
        is_cluster_gained = tile_xy in self._cluster_gained
        if is_new and is_cluster_gained:
            name = TileStyleName.NEW_TILE_NEW_CLUSTER
        elif is_cluster_gained:
            name = TileStyleName.VISITED_NEW_CLUSTER
        elif is_new:
            name = TileStyleName.NEW_TILE
        elif tile_xy in self._old_cluster_tiles:
            name = TileStyleName.OLD_CLUSTER
        elif tile_xy in self.tile_visits:
            name = TileStyleName.VISITED
        else:
            return None
        return _styled(self._styles, name)


class SquarePlannerColorStrategy(ColorStrategy):
    def __init__(
        self,
        tile_visits,
        styles: TileStyleSpecs,
        square_x: int,
        square_y: int,
        square_size: int,
    ):
        self.tile_visits = tile_visits
        self._styles = styles
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
            return _styled(self._styles, TileStyleName.VISITED)
        else:
            return None


class HighlightTiles(NamedTuple):
    new_tiles: frozenset[tuple[int, int]]
    cluster_gained: frozenset[tuple[int, int]]
    old_cluster_tiles: frozenset[tuple[int, int]]


def _cluster_context(
    zoom: int, activity_ids: AbstractSet[int]
) -> tuple[frozenset[tuple[int, int]], frozenset[tuple[int, int]]]:
    """Cluster tiles the activities gained, and the cluster before the earliest.

    The backdrop has to predate the *first* of the activities. Taking each
    activity's own cutoff would let an earlier ride's gains count as
    pre-existing for a later one on the same day.
    """
    gained: set[tuple[int, int]] = set()
    first_events: list[int] = []
    for activity_id in activity_ids:
        gained |= get_cluster_tiles_gained_by_activity(zoom, activity_id)
        first_event, _last_event = get_cluster_history_cutoff_for_activity(
            zoom, activity_id
        )
        if first_event is not None:
            first_events.append(first_event)
    old_cluster_tiles = (
        get_cluster_tiles_at_cutoff(zoom, min(first_events) - 1)
        if first_events
        else set()
    )
    return frozenset(gained), frozenset(old_cluster_tiles)


@functools.lru_cache(maxsize=32)
def _activity_highlight_tiles(
    zoom: int, activity_id: int, history_version: int
) -> HighlightTiles:
    """What a single activity discovered and clustered.

    Both lookups are indexed queries, but a viewport asks for many tile images
    at once, so the cache saves the repeated round trips. The history version is
    part of the key so that added activities invalidate stale entries.
    """
    new_tiles = frozenset(
        (tile_visit.tile_x, tile_visit.tile_y)
        for tile_visit in get_first_visits_for_activity(activity_id, zoom)
    )
    return HighlightTiles(new_tiles, *_cluster_context(zoom, {activity_id}))


@functools.lru_cache(maxsize=32)
def _day_highlight_tiles(
    zoom: int, day: datetime.date, history_version: int
) -> HighlightTiles:
    """What a whole local day discovered and clustered.

    Tiles are taken by their own first-visit date rather than through the
    activities, so a tour spanning midnight contributes only what it found on
    this day.
    """
    return HighlightTiles(
        get_new_tiles_on_day(zoom, day),
        *_cluster_context(zoom, get_new_tiles_activity_ids_on_day(zoom, day)),
    )


def clear_highlight_caches() -> None:
    """Drop the memoized highlights, which outlive the data they came from.

    The history version invalidates them as activities arrive, but it starts at
    zero for every database, so a database replaced within one process would
    otherwise keep answering from the previous one.
    """
    _activity_highlight_tiles.cache_clear()
    _day_highlight_tiles.cache_clear()


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
    filtered_state: Any | None = None,
    inaccessible_tiles: AbstractSet[tuple[int, int]] = frozenset(),
) -> ColorStrategy:
    color_strategy_name = request.args.get("color_strategy", "colorful_cluster")
    if color_strategy_name == "default":
        color_strategy_name = config.cluster_color_strategy
    styles = get_tile_style_specs()
    match color_strategy_name:
        case "max_cluster":
            if historical_state is not None:
                return HistoricalMaxClusterColorStrategy(historical_state, styles)
            if filtered_state is not None:
                return MaxClusterColorStrategy(
                    filtered_state.membership,
                    filtered_state.max_cluster_id,
                    tile_visits,
                    styles,
                )
            membership = get_cluster_membership_in_bounds(
                zoom, tx_min, tx_max, ty_min, ty_max
            )
            max_cluster_id, _ = get_max_cluster(zoom)
            return MaxClusterColorStrategy(
                membership, max_cluster_id, tile_visits, styles
            )
        case "colorful_cluster":
            if historical_state is not None:
                return HistoricalColorfulClusterColorStrategy(
                    historical_state, config, styles
                )
            membership = (
                filtered_state.membership
                if filtered_state is not None
                else get_cluster_membership_in_bounds(
                    zoom, tx_min, tx_max, ty_min, ty_max
                )
            )
            return ColorfulClusterColorStrategy(membership, tile_visits, config, styles)
        case "first":
            return VisitTimeColorStrategy(tile_visits, config, styles, use_first=True)
        case "last":
            return VisitTimeColorStrategy(tile_visits, config, styles, use_first=False)
        case "visits":
            return NumVisitsColorStrategy(tile_visits, config)
        case "missing":
            return MissingColorStrategy(tile_visits, styles, inaccessible_tiles)
        case "visited":
            return VisitedColorStrategy(tile_visits, styles)
        case "latest_new":
            history_version = get_cluster_history_latest_event_index(zoom)
            activity_id = request.args.get("activity_id", type=int)
            if activity_id is not None:
                highlight = _activity_highlight_tiles(
                    zoom, activity_id, history_version
                )
            else:
                day = get_latest_new_tiles_day(zoom)
                highlight = (
                    _day_highlight_tiles(zoom, day, history_version)
                    if day is not None
                    else HighlightTiles(frozenset(), frozenset(), frozenset())
                )
            return ActivityHighlightColorStrategy(
                highlight.new_tiles,
                highlight.cluster_gained,
                highlight.old_cluster_tiles,
                tile_visits,
                styles,
            )
        case "square_planner":
            return SquarePlannerColorStrategy(
                tile_visits,
                styles,
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
    grid_color: np.ndarray,
    min_width_px: int,
) -> None:
    if draw_left and width >= min_width_px:
        result[:, x_start, :] = grid_color
    if draw_top and width >= min_width_px:
        result[y_start, :, :] = grid_color


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


class _SubTile(NamedTuple):
    tile_x: int
    tile_y: int
    x_start: int
    y_start: int
    width: int
    draw_left: bool
    draw_top: bool
    draw_right: bool
    draw_bottom: bool


def _sub_tiles(zoom: int, z: int, x: int, y: int) -> list[_SubTile]:
    """Explorer tiles covered by one map tile, with their pixel extents."""
    if z >= zoom:
        factor = 2 ** (z - zoom)
        return [
            _SubTile(
                x // factor,
                y // factor,
                0,
                0,
                OSM_TILE_SIZE,
                x % factor == 0,
                y % factor == 0,
                (x + 1) % factor == 0,
                (y + 1) % factor == 0,
            )
        ]
    factor = 2 ** (zoom - z)
    width = OSM_TILE_SIZE // factor
    return [
        _SubTile(
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


def render_inaccessible_tile_image(
    zoom: int, z: int, x: int, y: int, inaccessible_tiles: frozenset[tuple[int, int]]
) -> np.ndarray:
    result = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE, 4), dtype=np.float32)
    pattern = _styled(get_tile_style_specs(), TileStyleName.INACCESSIBLE)
    for sub_tile in _sub_tiles(zoom, z, x, y):
        if (sub_tile.tile_x, sub_tile.tile_y) in inaccessible_tiles:
            result[
                sub_tile.y_start : sub_tile.y_start + sub_tile.width,
                sub_tile.x_start : sub_tile.x_start + sub_tile.width,
            ] = pattern.rasterize((sub_tile.width, sub_tile.width))
    return result


def render_activity_lines_tile_image(
    time_series: Iterable[pd.DataFrame], z: int, x: int, y: int, line_color: str
) -> np.ndarray:
    """Draw the tracks of one or more activities into a raster tile.

    The tracks share one mask, so overlapping recordings of the same route come
    out as a single line rather than a darker one.
    """
    mask = Image.new("L", (OSM_TILE_SIZE, OSM_TILE_SIZE))
    draw = ImageDraw.Draw(mask)
    line_width = min(6, max(2, z - 10))
    for series in time_series:
        for _segment_id, group in series.groupby("segment_id"):
            pixels = (
                np.array([group["x"] * 2**z - x, group["y"] * 2**z - y]).T
                * OSM_TILE_SIZE
            )
            if len(pixels) < 2:
                continue
            draw.line(
                [(px, py) for px, py in pixels],
                fill=255,
                width=line_width,
                joint="curve",
            )
    result = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE, 4), dtype=np.float32)
    result[:, :, :3] = hex_color_to_float(line_color + "ff").reshape(4)[:3]
    result[:, :, 3] = np.array(mask, dtype=np.float32) / 255.0
    return result


def _render_tile_image(
    zoom: int,
    z: int,
    x: int,
    y: int,
    color_strategy: ColorStrategy,
    evolution_state: SimpleNamespace,
    ui_config: UiConfig,
) -> np.ndarray:
    result = np.zeros((OSM_TILE_SIZE, OSM_TILE_SIZE, 4), dtype=np.float32)
    grid_color = hex_color_to_float(ui_config.explorer_grid_line_color).reshape(4)
    grid_min_width_px = ui_config.explorer_grid_line_min_width_px

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
    ) in _sub_tiles(zoom, z, x, y):
        tile_xy = (tile_x, tile_y)
        pattern = color_strategy.color(tile_xy)
        if pattern is not None:
            result[
                y_start : y_start + width,
                x_start : x_start + width,
            ] = pattern.rasterize((width, width))

        _draw_grid_lines(
            result,
            x_start,
            y_start,
            width,
            draw_left,
            draw_top,
            grid_color,
            grid_min_width_px,
        )
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
