import math
import pathlib
import time
from typing import Dict
from typing import Set
from typing import Tuple

import click
import requests
from PIL import Image
from PIL import ImageEnhance

from geo_activity_playground.core.cache_dir import cache_dir


def download_file(url: str, destination: pathlib.Path):
    if not destination.parent.exists():
        destination.parent.mkdir(exist_ok=True, parents=True)
    print(url)
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


def build_image(
    center_x: float,
    center_y: float,
    explored: Set[Tuple[int, int]],
    brightness: float = 1.0,
    width: int = 1920,
    height: int = 1080,
) -> Image.Image:
    tile_pixels = 256
    img = Image.new("RGB", (width, height))

    x_0 = center_x + 0.5 - width / (2 * tile_pixels)
    y_0 = center_y + 0.5 - height / (2 * tile_pixels)

    min_tile_x = math.floor(x_0)
    min_tile_y = math.floor(y_0)

    offset_x = int((min_tile_x - x_0) * tile_pixels)
    offset_y = int((min_tile_y - y_0) * tile_pixels)

    for i in range(0, int(width / tile_pixels + 2)):
        for j in range(0, int(width / tile_pixels + 2)):
            tile = (min_tile_x + i, min_tile_y + j)
            sprite = get_tile(14, tile[0], tile[1])
            if tile not in explored:
                enhancer = ImageEnhance.Brightness(sprite)
                sprite = enhancer.enhance(0.3)
            box = (offset_x + i * tile_pixels, offset_y + j * tile_pixels)
            img.paste(sprite, box)

    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness)

    return img


@click.command()
def main():
    img = build_image(8509.8, 5503.3, {(8509, 5503)})
    img.save("test.png")


if __name__ == "__main__":
    main()
