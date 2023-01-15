import math
import pathlib
import time
from typing import Dict
from typing import Tuple

import numpy as np
import requests
from PIL import Image

from geo_activity_playground.core.cache_dir import cache_dir


def compute_tile(lat: float, lon: float, zoom: int = 14) -> Tuple[int, int]:
    x = np.radians(lon)
    y = np.arcsinh(np.tan(np.radians(lat)))
    x = (1 + x / np.pi) / 2
    y = (1 - y / np.pi) / 2
    n = 2**zoom
    return int(x * n), int(y * n)


def get_tile_upper_left_lat_lon(
    tile_x: int, tile_y: int, zoom: int
) -> Tuple[float, float]:
    n = 2.0**zoom
    lon_deg = tile_x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * tile_y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def download_file(url: str, destination: pathlib.Path):
    if not destination.parent.exists():
        destination.parent.mkdir(exist_ok=True, parents=True)
    r = requests.get(url, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    with open(destination, "wb") as f:
        f.write(r.content)
    time.sleep(0.1)


def get_tile(
    zoom: int, x: int, y: int, _cache: Dict[Tuple[int, int, int], Image.Image] = {}
) -> Image.Image:
    if (zoom, x, y) in _cache:
        return _cache[(zoom, x, y)]
    destination = cache_dir / "osm_tiles" / f"{zoom}/{x}/{y}.png"
    if not destination.exists():
        url = f"https://maps.wikimedia.org/osm-intl/{zoom}/{x}/{y}.png"
        # url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        download_file(url, destination)
    with Image.open(destination) as image:
        image.load()
        image = image.convert("RGB")
    _cache[(zoom, x, y)] = image
    return image
