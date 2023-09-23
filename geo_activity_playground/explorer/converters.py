import pathlib

import pandas as pd
from tqdm import tqdm

from ..core.tiles import compute_tile
from geo_activity_playground.core.sources import TimeSeriesSource


def get_tile_history(ts_source: TimeSeriesSource) -> pd.DataFrame:
    explorer_cache_dir = pathlib.Path("Explorer Cache") / "Per Activity"
    explorer_cache_dir.mkdir(exist_ok=True, parents=True)

    for activity in tqdm(ts_source.iter_activities(), desc="Extract explorer tiles"):
        target_path = explorer_cache_dir / f"{activity.name}.parquet"
        if not target_path.exists():
            tiles = tiles_from_points(activity)
            first_tiles = first_time_per_tile(tiles)
            first_tiles.to_parquet(target_path)

    tiles = pd.DataFrame()
    for path in tqdm(explorer_cache_dir.glob("*.parquet"), desc="Build tile history"):
        shard = pd.read_parquet(path)
        tiles = pd.concat([tiles, shard])
        tiles = first_time_per_tile(tiles)
    tiles.to_parquet(explorer_cache_dir.parent / "first_time_per_tile.parquet")
    return tiles


def tiles_from_points(points: pd.DataFrame) -> pd.DataFrame:
    new_rows = []
    for index, row in points.iterrows():
        tile = compute_tile(row["latitude"], row["longitude"])
        new_rows.append((row["time"],) + tile)
    return pd.DataFrame(new_rows, columns=["time", "tile_x", "tile_y"])


def first_time_per_tile(tiles: pd.DataFrame) -> pd.DataFrame:
    reduced = tiles.groupby(["tile_x", "tile_y"]).min().reset_index()
    return reduced
