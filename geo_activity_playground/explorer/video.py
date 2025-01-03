import dataclasses
import math
import pathlib
from typing import Generator
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageEnhance
from tqdm import tqdm

from ..core.raster_map import get_tile

# import scipy.interpolate


def build_image(
    center_x: float,
    center_y: float,
    explored: Set[Tuple[int, int]],
    brightness: float = 1.0,
    width: int = 1920,
    height: int = 1080,
    frame_counter: int = 0,
) -> Optional[Image.Image]:
    path = pathlib.Path(f"video/{frame_counter:06d}.png")
    if path.exists():
        return None
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

    path.parent.mkdir(exist_ok=True)
    img.save(path)
    return img


def chunk_tiles(tiles: pd.DataFrame) -> List[List[Tuple[int, int]]]:
    last_x, last_y = -1000, -1000
    chunks: List[List[Tuple[int, int]]] = []
    chunk: List[Tuple[int, int]] = []
    for index, row in tiles.iterrows():
        x, y = row["Tile X"], row["Tile Y"]
        if abs(x - last_x) + abs(y - last_y) > 3:
            if chunk:
                chunks.append(chunk)
                chunk = []
        chunk.append((x, y))
        last_x, last_y = x, y
    return chunks


@dataclasses.dataclass
class RenderArguments:
    center_x: float
    center_y: float
    explored: Set[Tuple[int, int]]
    brightness: float


def animate_chunk(
    chunk: List[Tuple[int, int]], explored: Set[Tuple[int, int]]
) -> Generator[RenderArguments, None, None]:
    if len(chunk) == 1:
        x, y = chunk[0]
        explored.add((x, y))
        yield RenderArguments(x, y, explored, 1.0)
    else:
        coords = np.array(chunk).T
        tck, u = scipy.interpolate.splprep(coords, k=min(len(chunk) - 1, 3))
        u2 = np.linspace(0.0, 1.0, 25 * len(chunk))

        interp_x, interp_y = scipy.interpolate.splev(u2, tck)

        for uu, ix, iy in tqdm(list(zip(u2, interp_x, interp_y)), desc="Animation"):
            passed = u <= uu
            passed[0] = uu > 0
            for coord in chunk[: sum(passed)]:
                explored.add(coord)
            yield RenderArguments(ix, iy, explored, 1.0)


def explorer_video_main():
    tile_df = pd.read_json(cache_dir / "tiles.json", date_unit="ns").sort_values("Time")
    chunks = chunk_tiles(tile_df)
    frame_counter = 0
    explored = set()
    for chunk in tqdm(chunks, desc="Chunk"):
        for frame_id, frame in enumerate(animate_chunk(chunk, explored)):
            if frame_id == 0:
                for brightness in tqdm(np.linspace(0.0, 1.0, 25), desc="Fade-In"):
                    build_image(
                        frame.center_x,
                        frame.center_y,
                        explored - set(chunk[0]),
                        brightness,
                        frame_counter=frame_counter,
                    )
                    frame_counter += 1
            build_image(
                frame.center_x,
                frame.center_y,
                frame.explored,
                frame.brightness,
                frame_counter=frame_counter,
            )
            frame_counter += 1
        for brightness in tqdm(np.linspace(1.0, 0.0, 25), desc="Fade-Out"):
            build_image(
                frame.center_x,
                frame.center_y,
                explored,
                brightness,
                frame_counter=frame_counter,
            )
            frame_counter += 1
