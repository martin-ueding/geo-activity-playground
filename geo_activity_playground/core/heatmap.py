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

    @property
    def shape(self) -> tuple[int, int]:
        return (
            (self.y_tile_max - self.y_tile_min) * OSM_TILE_SIZE,
            (self.x_tile_max - self.x_tile_min) * OSM_TILE_SIZE,
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
    background = np.zeros((*tile_bounds.shape, 3))

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


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
    image = np.dstack((image, image, image))
    return image


def crop_image_to_bounds(
    image: np.ndarray, geo_bounds: GeoBounds, tile_bounds: TileBounds
) -> np.ndarray:
    min_x, min_y = compute_tile_float(
        geo_bounds.lat_max, geo_bounds.lon_min, tile_bounds.zoom
    )
    max_x, max_y = compute_tile_float(
        geo_bounds.lat_min, geo_bounds.lon_max, tile_bounds.zoom
    )

    crop_mask = TileBounds(
        tile_bounds.zoom,
        int((min_x - tile_bounds.x_tile_min) * OSM_TILE_SIZE),
        int((max_x - tile_bounds.x_tile_min) * OSM_TILE_SIZE),
        int((min_y - tile_bounds.y_tile_min) * OSM_TILE_SIZE),
        int((max_y - tile_bounds.y_tile_min) * OSM_TILE_SIZE),
    )
    crop_mask = make_bounds_square(crop_mask)

    image = image[
        crop_mask.y_tile_min : crop_mask.y_tile_max,
        crop_mask.x_tile_min : crop_mask.x_tile_max,
        :,
    ]
    return image


def make_bounds_square(bounds: TileBounds) -> TileBounds:
    x_radius = (bounds.x_tile_max - bounds.x_tile_min) / 2
    y_radius = (bounds.y_tile_max - bounds.y_tile_min) / 2
    x_center = (bounds.x_tile_max + bounds.x_tile_min) / 2
    y_center = (bounds.y_tile_max + bounds.y_tile_min) / 2

    radius = max(x_radius, y_radius)

    return TileBounds(
        x_tile_min=int(x_center - radius),
        y_tile_min=int(y_center - radius),
        x_tile_max=int(x_center + radius),
        y_tile_max=int(y_center + radius),
        zoom=bounds.zoom,
    )
