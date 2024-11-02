"""
This code is based on https://github.com/remisalmon/Strava-local-heatmap.
"""
import dataclasses
import logging

import numpy as np

from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class GeoBounds:
    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float


def get_bounds(lat_lon_data: np.ndarray) -> GeoBounds:
    return GeoBounds(*np.min(lat_lon_data, axis=0), *np.max(lat_lon_data, axis=0))


def add_margin(lower: float, upper: float) -> tuple[float, float]:
    spread = upper - lower
    margin = spread / 20
    return max(0.0, lower - margin), upper + margin


def add_margin_to_geo_bounds(bounds: GeoBounds) -> GeoBounds:
    lat_min, lat_max = add_margin(bounds.lat_min, bounds.lat_max)
    lon_min, lon_max = add_margin(bounds.lon_min, bounds.lon_max)
    return GeoBounds(lat_min, lon_min, lat_max, lon_max)


OSM_TILE_SIZE = 256  # OSM tile size in pixel
OSM_MAX_ZOOM = 19  # OSM maximum zoom level
MAX_TILE_COUNT = 2000  # maximum number of tiles to download


@dataclasses.dataclass
class TileBounds:
    zoom: int
    x_tile_min: int
    x_tile_max: int
    y_tile_min: int
    y_tile_max: int


@dataclasses.dataclass
class PixelBounds:
    x_min: int
    x_max: int
    y_min: int
    y_max: int

    @classmethod
    def from_tile_bounds(cls, tile_bounds: TileBounds) -> "PixelBounds":
        return cls(
            int(tile_bounds.x_tile_min) * OSM_TILE_SIZE,
            int(tile_bounds.x_tile_max) * OSM_TILE_SIZE,
            int(tile_bounds.y_tile_min) * OSM_TILE_SIZE,
            int(tile_bounds.y_tile_max) * OSM_TILE_SIZE,
        )

    @property
    def shape(self) -> tuple[int, int]:
        return (
            self.y_max - self.y_min,
            self.x_max - self.x_min,
        )


def geo_bounds_from_tile_bounds(tile_bounds: TileBounds) -> GeoBounds:
    lat_max, lon_min = get_tile_upper_left_lat_lon(
        tile_bounds.x_tile_min, tile_bounds.y_tile_min, tile_bounds.zoom
    )
    lat_min, lon_max = get_tile_upper_left_lat_lon(
        tile_bounds.x_tile_max, tile_bounds.y_tile_max, tile_bounds.zoom
    )
    return GeoBounds(lat_min, lon_min, lat_max, lon_max)


def get_sensible_zoom_level(
    bounds: GeoBounds, picture_size: tuple[int, int]
) -> TileBounds:
    zoom = OSM_MAX_ZOOM

    while True:
        x_tile_min, y_tile_max = map(
            int, compute_tile_float(bounds.lat_min, bounds.lon_min, zoom)
        )
        x_tile_max, y_tile_min = map(
            int, compute_tile_float(bounds.lat_max, bounds.lon_max, zoom)
        )

        x_tile_max += 1
        y_tile_max += 1

        if (x_tile_max - x_tile_min) * OSM_TILE_SIZE <= picture_size[0] and (
            y_tile_max - y_tile_min
        ) * OSM_TILE_SIZE <= picture_size[1]:
            break

        zoom -= 1

    tile_count = (x_tile_max - x_tile_min) * (y_tile_max - y_tile_min)

    if tile_count > MAX_TILE_COUNT:
        raise RuntimeError("Zoom value too high, too many tiles to download")

    return TileBounds(
        zoom=zoom,
        x_tile_min=x_tile_min,
        x_tile_max=x_tile_max,
        y_tile_min=y_tile_min,
        y_tile_max=y_tile_max,
    )


def build_map_from_tiles(tile_bounds: TileBounds) -> np.ndarray:
    background = np.zeros((*PixelBounds.from_tile_bounds(tile_bounds).shape, 3))

    for x in range(tile_bounds.x_tile_min, tile_bounds.x_tile_max):
        for y in range(tile_bounds.y_tile_min, tile_bounds.y_tile_max):
            tile = np.array(get_tile(tile_bounds.zoom, x, y)) / 255

            i = y - tile_bounds.y_tile_min
            j = x - tile_bounds.x_tile_min

            background[
                i * OSM_TILE_SIZE : (i + 1) * OSM_TILE_SIZE,
                j * OSM_TILE_SIZE : (j + 1) * OSM_TILE_SIZE,
                :,
            ] = tile[:, :, :3]

    return background


def build_map_from_tiles_around_center(
    center: tuple[float, float],
    zoom: int,
    target: tuple[int, int],
    inner_target: tuple[int, int],
) -> np.ndarray:
    background = np.zeros((target[1], target[0], 3))

    # We will work with the center point and have it in terms of tiles `t` and also in terms of pixels `p`. At the start we know that the tile center must be in the middle of the image.
    t = np.array(center)
    p = np.array([inner_target[0] / 2, inner_target[1] / 2])

    # Shift both such that they are in the top-left corner of an even tile.
    t_offset = np.array([center[0] % 1, center[1] % 1])
    t -= t_offset
    p -= t_offset * OSM_TILE_SIZE

    # Shift until we have left the image.
    shift = np.ceil(p / OSM_TILE_SIZE)
    p -= shift * OSM_TILE_SIZE
    t -= shift

    num_tiles = np.ceil(np.array(target) / OSM_TILE_SIZE) + 1

    for x in range(int(t[0]), int(t[0] + num_tiles[0])):
        for y in range(int(t[1]), int(t[1]) + int(num_tiles[1])):
            source_x_min = 0
            source_y_min = 0
            source_x_max = source_x_min + OSM_TILE_SIZE
            source_y_max = source_y_min + OSM_TILE_SIZE

            target_x_min = (x - int(t[0])) * OSM_TILE_SIZE + int(p[0])
            target_y_min = (y - int(t[1])) * OSM_TILE_SIZE + int(p[1])
            target_x_max = target_x_min + OSM_TILE_SIZE
            target_y_max = target_y_min + OSM_TILE_SIZE

            if target_x_min < 0:
                source_x_min -= target_x_min
                target_x_min = 0
            if target_y_min < 0:
                source_y_min -= target_y_min
                target_y_min = 0
            if target_x_max > target[0]:
                a = target_x_max - target[0]
                target_x_max -= a
                source_x_max -= a
            if target_y_max > target[1]:
                a = target_y_max - target[1]
                target_y_max -= a
                source_y_max -= a

            if source_x_max < 0 or source_y_max < 0:
                continue

            tile = np.array(get_tile(zoom, x, y)) / 255

            background[target_y_min:target_y_max, target_x_min:target_x_max] = tile[
                source_y_min:source_y_max, source_x_min:source_x_max, :3
            ]

    return background


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
    image = np.dstack((image, image, image))
    return image
