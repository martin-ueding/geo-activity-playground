import pathlib

import pandas as pd

from ..core.cache_dir import cache_dir
from ..core.tiles import compute_tile
from ..strava.importing import read_activity
from ..strava.importing import strava_checkout_path


def generate_tile_history() -> None:
    activities_path = strava_checkout_path / "activities"
    for path in activities_path.glob("*"):
        tile_path = cache_dir / f"tiles-{path.stem.split('.')[0]}.json"
        if tile_path.exists() and tile_path.stat().st_mtime > path.stat().st_mtime:
            continue
        activity = read_activity(path)
        tiles = tiles_from_points(activity)
        first_tiles = first_time_per_tile(tiles)
        first_tiles.to_json(tile_path, date_unit="ns")


def combine_tile_history() -> None:
    tiles = pd.DataFrame()
    for path in cache_dir.glob("tiles-*.json"):
        shard = pd.read_json(path)
        pd.to_datetime(shard.Time)
        tiles = pd.concat([tiles, shard])
        tiles = first_time_per_tile(tiles)
    tiles.to_json(cache_dir / "tiles.json", date_unit="ns")


def tiles_from_points(points: pd.DataFrame) -> pd.DataFrame:
    new_rows = []
    for index, row in points.iterrows():
        tile = compute_tile(row["Latitude"], row["Longitude"])
        new_rows.append((row["Time"],) + tile)
    return pd.DataFrame(new_rows, columns=["Time", "Tile X", "Tile Y"])


def first_time_per_tile(tiles: pd.DataFrame) -> pd.DataFrame:
    reduced = tiles.groupby(["Tile X", "Tile Y"]).min().reset_index()
    return reduced
