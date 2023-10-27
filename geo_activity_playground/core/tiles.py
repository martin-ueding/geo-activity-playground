import math
import pathlib
import time

import numpy as np
import requests
from PIL import Image


def compute_tile(lat: float, lon: float, zoom: int = 14) -> tuple[int, int]:
    x = np.radians(lon)
    y = np.arcsinh(np.tan(np.radians(lat)))
    x = (1 + x / np.pi) / 2
    y = (1 - y / np.pi) / 2
    n = 2**zoom
    return int(x * n), int(y * n)


def get_tile_upper_left_lat_lon(
    tile_x: int, tile_y: int, zoom: int
) -> tuple[float, float]:
    n = 2.0**zoom
    lon_deg = tile_x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * tile_y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def download_file(url: str, destination: pathlib.Path):
    print(f"Downloading {url} …")
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


def get_tile(
    zoom: int, x: int, y: int, _cache: dict[tuple[int, int, int], Image.Image] = {}
) -> Image.Image:
    if (zoom, x, y) in _cache:
        return _cache[(zoom, x, y)]
    destination = pathlib.Path.cwd() / "Open Street Map Tiles" / f"{zoom}/{x}/{y}.png"
    if not destination.exists():
        # url = f"https://maps.wikimedia.org/osm-intl/{zoom}/{x}/{y}.png"
        url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        download_file(url, destination)
    with Image.open(destination) as image:
        image.load()
        image = image.convert("RGB")
    _cache[(zoom, x, y)] = image
    return image


def latlon_to_xy(lat_deg: float, lon_deg: float, zoom: int) -> tuple[float, float]:
    """
    Based on https://github.com/remisalmon/Strava-local-heatmap.
    """
    lat_rad = np.radians(lat_deg)
    n = 2.0**zoom
    x = (lon_deg + 180.0) / 360.0 * n
    y = (1.0 - np.arcsinh(np.tan(lat_rad)) / np.pi) / 2.0 * n
    return x, y


def xy_to_latlon(x: float, y: float, zoom: int) -> tuple[float, float]:
    """
    Returns (lat, lon) in degree from OSM coordinates (x,y) rom https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames

    Based on https://github.com/remisalmon/Strava-local-heatmap.
    """
    n = 2.0**zoom
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * y / n)))
    lat_deg = float(np.degrees(lat_rad))
    return lat_deg, lon_deg
