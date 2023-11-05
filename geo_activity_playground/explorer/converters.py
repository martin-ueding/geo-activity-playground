import functools
import pathlib

import pandas as pd

from ..core.tiles import compute_tile
from geo_activity_playground.core.sources import TimeSeriesSource


@functools.cache
def get_tile_history(ts_source: TimeSeriesSource) -> pd.DataFrame:
    tiles = pd.DataFrame()
    for activity in ts_source.iter_activities():
        shard = get_first_tiles(activity)
        if not len(shard):
            continue
        tiles = pd.concat([tiles, shard])
        tiles = first_time_per_tile(tiles)

    explorer_cache_dir = pathlib.Path("Explorer")
    explorer_cache_dir.mkdir(exist_ok=True, parents=True)
    tiles.to_parquet(explorer_cache_dir / "first_time_per_tile.parquet")
    return tiles


def get_first_tiles(activity: pd.DataFrame) -> pd.DataFrame:
    explorer_cache_dir = pathlib.Path("Explorer") / "Per Activity"
    explorer_cache_dir.mkdir(exist_ok=True, parents=True)
    target_path = explorer_cache_dir / f"{activity.name}.parquet"

    if target_path.exists():
        return pd.read_parquet(target_path)
    else:
        tiles = tiles_from_points(activity)
        first_tiles = first_time_per_tile(tiles)
        first_tiles.to_parquet(target_path)
        return first_tiles


def tiles_from_points(points: pd.DataFrame) -> pd.DataFrame:
    new_rows = []
    for index, row in points.iterrows():
        tile = compute_tile(row["latitude"], row["longitude"])
        new_rows.append((row["time"],) + tile)
    return pd.DataFrame(new_rows, columns=["time", "tile_x", "tile_y"])


def first_time_per_tile(tiles: pd.DataFrame) -> pd.DataFrame:
    reduced = tiles.groupby(["tile_x", "tile_y"]).min().reset_index()
    return reduced
