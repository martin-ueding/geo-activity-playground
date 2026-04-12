import dataclasses
import math
import os
import pathlib

import numpy as np
import pandas as pd
import sqlalchemy as sa
from PIL import Image, ImageEnhance
from tqdm import tqdm

from ..core.config import ConfigAccessor
from ..core.raster_map import get_tile


@dataclasses.dataclass
class ExplorerVideoOptions:
    basedir: pathlib.Path
    zoom: int = 14
    width: int = 1920
    height: int = 1080
    fps: int = 30
    output_path: pathlib.Path | None = None
    steps_per_tile: int = 12
    fade_frames: int = 12
    map_tile_url: str | None = None


@dataclasses.dataclass(frozen=True)
class FrameSpec:
    center_x: float
    center_y: float
    brightness: float
    new_tiles: tuple[tuple[int, int], ...] = ()


def load_tile_history(database_path: pathlib.Path, zoom: int) -> pd.DataFrame:
    engine = sa.create_engine(f"sqlite:///{database_path.absolute()}")
    try:
        with engine.connect() as connection:
            df = pd.read_sql_query(
                sa.text(
                    """
                    SELECT
                        first_activity_id AS activity_id,
                        first_time AS time,
                        tile_x,
                        tile_y
                    FROM tile_visits
                    WHERE zoom = :zoom
                    ORDER BY first_time, first_activity_id, tile_x, tile_y
                    """
                ),
                connection,
                params={"zoom": zoom},
            )
    finally:
        engine.dispose()
    if len(df) == 0:
        return pd.DataFrame(columns=["activity_id", "time", "tile_x", "tile_y"])
    df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
    return df


def chunk_tiles(tiles: pd.DataFrame) -> list[list[tuple[int, int]]]:
    if len(tiles) == 0:
        return []
    last_x, last_y = -1000, -1000
    chunks: list[list[tuple[int, int]]] = []
    chunk: list[tuple[int, int]] = []
    for row in tiles.itertuples(index=False):
        x, y = int(row.tile_x), int(row.tile_y)
        if abs(x - last_x) + abs(y - last_y) > 3 and len(chunk) > 0:
            chunks.append(chunk)
            chunk = []
        chunk.append((x, y))
        last_x, last_y = x, y
    if len(chunk) > 0:
        chunks.append(chunk)
    return chunks


def iter_chunk_frames(
    chunk: list[tuple[int, int]],
    *,
    steps_per_tile: int,
    fade_frames: int,
) -> list[FrameSpec]:
    frames: list[FrameSpec] = []
    if len(chunk) == 0:
        return frames

    first_x, first_y = chunk[0]
    if fade_frames > 0:
        for brightness in np.linspace(0.0, 1.0, fade_frames):
            frames.append(FrameSpec(first_x, first_y, float(brightness)))

    frames.append(FrameSpec(first_x, first_y, 1.0, new_tiles=((first_x, first_y),)))

    prev_x, prev_y = first_x, first_y
    for tile_x, tile_y in chunk[1:]:
        for step in range(1, steps_per_tile + 1):
            progress = step / steps_per_tile
            center_x = prev_x * (1 - progress) + tile_x * progress
            center_y = prev_y * (1 - progress) + tile_y * progress
            new_tiles = ((tile_x, tile_y),) if step == steps_per_tile else ()
            frames.append(FrameSpec(center_x, center_y, 1.0, new_tiles=new_tiles))
        prev_x, prev_y = tile_x, tile_y

    if fade_frames > 0:
        for brightness in np.linspace(1.0, 0.0, fade_frames):
            frames.append(FrameSpec(prev_x, prev_y, float(brightness)))
    return frames


def render_frame(
    *,
    zoom: int,
    center_x: float,
    center_y: float,
    explored: set[tuple[int, int]],
    brightness: float,
    width: int,
    height: int,
    map_tile_url: str,
) -> np.ndarray:
    tile_pixels = 256
    image = Image.new("RGB", (width, height))

    x0 = center_x + 0.5 - width / (2 * tile_pixels)
    y0 = center_y + 0.5 - height / (2 * tile_pixels)

    min_tile_x = math.floor(x0)
    min_tile_y = math.floor(y0)

    offset_x = int((min_tile_x - x0) * tile_pixels)
    offset_y = int((min_tile_y - y0) * tile_pixels)

    tiles_x = math.ceil(width / tile_pixels) + 2
    tiles_y = math.ceil(height / tile_pixels) + 2
    for i in range(tiles_x):
        for j in range(tiles_y):
            tile = (min_tile_x + i, min_tile_y + j)
            sprite = get_tile(zoom, tile[0], tile[1], map_tile_url)
            if tile not in explored:
                sprite = ImageEnhance.Brightness(sprite).enhance(0.3)
            box = (offset_x + i * tile_pixels, offset_y + j * tile_pixels)
            image.paste(sprite, box)

    if brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(brightness)
    return np.asarray(image, dtype=np.uint8)


def generate_explorer_video(options: ExplorerVideoOptions) -> pathlib.Path:
    import imageio.v2 as imageio

    os.chdir(options.basedir)
    config = ConfigAccessor()()
    map_tile_url = options.map_tile_url or config.map_tile_url
    database_path = pathlib.Path("database.sqlite")
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path.absolute()}")

    tile_df = load_tile_history(database_path=database_path, zoom=options.zoom)
    if len(tile_df) == 0:
        raise RuntimeError(
            f"No explorer tile history available for zoom {options.zoom}."
        )

    chunks = chunk_tiles(tile_df)
    output_path = options.output_path
    if output_path is None:
        output_path = pathlib.Path("Explorer Video") / f"explorer-z{options.zoom}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    explored: set[tuple[int, int]] = set()
    with imageio.get_writer(output_path, fps=options.fps) as writer:
        for chunk in tqdm(chunks, desc="Explorer video chunks"):
            for frame in iter_chunk_frames(
                chunk,
                steps_per_tile=options.steps_per_tile,
                fade_frames=options.fade_frames,
            ):
                explored.update(frame.new_tiles)
                data = render_frame(
                    zoom=options.zoom,
                    center_x=frame.center_x,
                    center_y=frame.center_y,
                    explored=explored,
                    brightness=frame.brightness,
                    width=options.width,
                    height=options.height,
                    map_tile_url=map_tile_url,
                )
                writer.append_data(data)
    return output_path


def explorer_video_main(options) -> None:
    output_path = generate_explorer_video(
        ExplorerVideoOptions(
            basedir=options.basedir,
            zoom=options.zoom,
            width=options.video_width,
            height=options.video_height,
            fps=options.fps,
            output_path=options.output_path,
            steps_per_tile=options.steps_per_tile,
            fade_frames=options.fade_frames,
            map_tile_url=options.map_tile_url,
        )
    )
    print(f"Wrote explorer video to {output_path}")
