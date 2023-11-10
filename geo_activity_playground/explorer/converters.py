import functools
import pathlib

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tiles import compute_tile


@functools.cache
def explorer_per_activity_cache_dir() -> pathlib.Path:
    path = pathlib.Path("Cache") / "Explorer Per Activity"
    path.mkdir(exist_ok=True, parents=True)
    return path


def get_first_tiles(id, repository: ActivityRepository) -> pd.DataFrame:
    target_path = explorer_per_activity_cache_dir() / f"{id}.parquet"
    if target_path.exists():
        return pd.read_parquet(target_path)
    else:
        time_series = repository.get_time_series(id)
        tiles = tiles_from_points(time_series)
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


@functools.cache
def get_tile_history(repository: ActivityRepository) -> pd.DataFrame:
    tiles = pd.DataFrame()
    for activity in repository.iter_activities():
        shard = get_first_tiles(activity.id, repository)
        if not len(shard):
            continue
        tiles = pd.concat([tiles, shard])
    tiles = first_time_per_tile(tiles)
    tiles.to_parquet("Cache/first_time_per_tile.parquet")
    return tiles
