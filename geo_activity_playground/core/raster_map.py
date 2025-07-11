import abc
import dataclasses
import functools
import logging
import pathlib
import time
import urllib.parse

import numpy as np
import requests
from PIL import Image

from .config import Config
from .tiles import compute_tile_float


logger = logging.getLogger(__name__)


OSM_TILE_SIZE = 256  # OSM tile size in pixel
OSM_MAX_ZOOM = 19  # OSM maximum zoom level
MAX_TILE_COUNT = 2000  # maximum number of tiles to download

## Basic data types ##


@dataclasses.dataclass
class GeoBounds:
    """
    Models an area on the globe as a rectangle of latitude and longitude.

    Latitude goes from South Pole (-90°) to North Pole (+90°). Longitude goes from West (-180°) to East (+180°). Be careful when converting latitude to Y-coordinates as increasing latitude will mean decreasing Y.
    """

    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float


@dataclasses.dataclass
class TileBounds:
    zoom: int
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


@dataclasses.dataclass
class PixelBounds:
    x1: int
    y1: int
    x2: int
    y2: int

    @classmethod
    def from_tile_bounds(cls, tile_bounds: TileBounds) -> "PixelBounds":
        return pixel_bounds_from_tile_bounds(tile_bounds)

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width


@dataclasses.dataclass
class RasterMapImage:
    image: np.ndarray
    tile_bounds: TileBounds
    geo_bounds: GeoBounds
    pixel_bounds: PixelBounds


## Converter functions ##


def pixel_bounds_from_tile_bounds(tile_bounds: TileBounds) -> PixelBounds:
    return PixelBounds(
        int(tile_bounds.x1 * OSM_TILE_SIZE),
        int(tile_bounds.y1 * OSM_TILE_SIZE),
        int(tile_bounds.x2 * OSM_TILE_SIZE),
        int(tile_bounds.y2 * OSM_TILE_SIZE),
    )


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

    return TileBounds(zoom, x_tile_min, y_tile_min, x_tile_max, y_tile_max)


@functools.lru_cache()
def get_tile(zoom: int, x: int, y: int, url_template: str) -> Image.Image:
    destination = osm_tile_path(x, y, zoom, url_template)
    if not destination.exists():
        logger.info(f"Downloading OSM tile {x=}, {y=}, {zoom=} …")
        url = url_template.format(x=x, y=y, zoom=zoom)
        download_file(url, destination)
    with Image.open(destination) as image:
        image.load()
        image = image.convert("RGB")
    return image


def tile_bounds_around_center(
    tile_center: tuple[float, float], pixel_size: tuple[int, int], zoom: int
) -> TileBounds:
    x, y = tile_center
    width = pixel_size[0] / OSM_TILE_SIZE
    height = pixel_size[1] / OSM_TILE_SIZE
    return TileBounds(
        zoom, x - width / 2, y - height / 2, x + width / 2, y + height / 2
    )


def _paste_array(
    target: np.ndarray, source: np.ndarray, offset_0: int, offset_1: int
) -> None:
    source_min_0 = 0
    source_min_1 = 0
    source_max_0 = source.shape[0]
    source_max_1 = source.shape[1]

    target_min_0 = offset_0
    target_min_1 = offset_1
    target_max_0 = offset_0 + source.shape[0]
    target_max_1 = offset_1 + source.shape[1]

    if target_min_1 < 0:
        source_min_1 -= target_min_1
        target_min_1 = 0
    if target_min_0 < 0:
        source_min_0 -= target_min_0
        target_min_0 = 0
    if target_max_1 > target.shape[1]:
        a = target_max_1 - target.shape[1]
        target_max_1 -= a
        source_max_1 -= a
    if target_max_0 > target.shape[0]:
        a = target_max_0 - target.shape[0]
        target_max_0 -= a
        source_max_0 -= a

    if source_max_1 < 0 or source_max_0 < 0:
        return

    target[target_min_0:target_max_0, target_min_1:target_max_1] = source[
        source_min_0:source_max_0, source_min_1:source_max_1
    ]


def map_image_from_tile_bounds(tile_bounds: TileBounds, config: Config) -> np.ndarray:
    pixel_bounds = pixel_bounds_from_tile_bounds(tile_bounds)
    background = np.zeros((pixel_bounds.height, pixel_bounds.width, 3))

    north_west = np.array([tile_bounds.x1, tile_bounds.y1])
    offset = north_west % 1
    tile_anchor = north_west - offset
    pixel_anchor: np.ndarray = np.array([0, 0]) - np.array(
        offset * OSM_TILE_SIZE, dtype=np.int64
    )

    num_tile_x = int(np.ceil(tile_bounds.width)) + 1
    num_tile_y = int(np.ceil(tile_bounds.height)) + 1

    for x in range(int(tile_anchor[0]), int(tile_anchor[0] + num_tile_x)):
        for y in range(int(tile_anchor[1]), int(tile_anchor[1]) + num_tile_y):
            tile = np.array(get_tile(tile_bounds.zoom, x, y, config.map_tile_url)) / 255
            _paste_array(
                background,
                tile,
                (y - int(tile_anchor[1])) * OSM_TILE_SIZE + int(pixel_anchor[1]),
                (x - int(tile_anchor[0])) * OSM_TILE_SIZE + int(pixel_anchor[0]),
            )

    return background


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
    image = np.dstack((image, image, image))
    return image


def osm_tile_path(x: int, y: int, zoom: int, url_template: str) -> pathlib.Path:
    base_dir = pathlib.Path("Open Street Map Tiles")
    dir_for_source = base_dir / urllib.parse.quote_plus(url_template)
    path = dir_for_source / f"{zoom}/{x}/{y}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def download_file(url: str, destination: pathlib.Path):
    if not destination.parent.exists():
        destination.parent.mkdir(exist_ok=True, parents=True)
    r = requests.get(
        url,
        allow_redirects=True,
        headers={"User-Agent": "Martin's Geo Activity Playground"},
    )
    assert r.ok
    with open(destination, "wb") as f:
        f.write(r.content)
    time.sleep(0.1)


class TileGetter:
    def __init__(self, map_tile_url: str):
        self._map_tile_url = map_tile_url

    def get_tile(
        self,
        z: int,
        x: int,
        y: int,
    ):
        return get_tile(z, x, y, self._map_tile_url)


class ImageTransform:
    @abc.abstractmethod
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        pass


class IdentityImageTransform(ImageTransform):
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        return image


class GrayscaleImageTransform(ImageTransform):
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        return np.dstack((image, image, image))  # to rgb


class PastelImageTransform(ImageTransform):
    def __init__(self, factor: float = 0.7):
        self._factor = factor

    def transform_image(self, image: np.ndarray) -> np.ndarray:
        averaged_tile = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
        grayscale_tile = np.dstack((averaged_tile, averaged_tile, averaged_tile))
        return self._factor * grayscale_tile + (1 - self._factor) * image


class InverseGrayscaleImageTransform(ImageTransform):
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        return 1 - np.dstack((image, image, image))  # to rgb
