import functools
import logging
import pathlib

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import work_tracker
from geo_activity_playground.core.tiles import compute_tile


logger = logging.getLogger(__name__)


@functools.cache
def explorer_per_activity_cache_dir() -> pathlib.Path:
    path = pathlib.Path("Cache") / "Explorer Per Activity"
    path.mkdir(exist_ok=True, parents=True)
    return path


def get_first_tiles(id, repository: ActivityRepository, zoom: int) -> pd.DataFrame:
    target_path = explorer_per_activity_cache_dir() / str(zoom) / f"{id}.parquet"
    if target_path.exists():
        return pd.read_parquet(target_path)
    else:
        logger.info(f"Extracting tiles from activity {id} …")
        time_series = repository.get_time_series(id)
        tiles = tiles_from_points(time_series, zoom)
        first_tiles = first_time_per_tile(tiles)
        target_path.parent.mkdir(exist_ok=True, parents=True)
        first_tiles.to_parquet(target_path)
        return first_tiles


def tiles_from_points(points: pd.DataFrame, zoom: int) -> pd.DataFrame:
    assert pd.api.types.is_dtype_equal(points["time"].dtype, "datetime64[ns, UTC]")
    new_rows = []
    for index, row in points.iterrows():
        if "latitude" in row.keys() and "longitude" in row.keys():
            tile = compute_tile(row["latitude"], row["longitude"], zoom)
            new_rows.append((row["time"],) + tile)
    return pd.DataFrame(new_rows, columns=["time", "tile_x", "tile_y"])


def first_time_per_tile(tiles: pd.DataFrame) -> pd.DataFrame:
    reduced = tiles.groupby(["tile_x", "tile_y"]).min().reset_index()
    return reduced


@functools.cache
def get_tile_history(repository: ActivityRepository, zoom: int) -> pd.DataFrame:
    logger.info("Building explorer tile history from all activities …")

    cache_file = pathlib.Path(f"Cache/first_time_per_tile_{zoom}.parquet")
    if cache_file.exists():
        tiles = pd.read_parquet(cache_file)
    else:
        tiles = pd.DataFrame()

    with work_tracker(
        pathlib.Path(f"Cache/task_first_time_per_tile_{zoom}.json")
    ) as parsed_activities:
        for activity in repository.iter_activities(new_to_old=False):
            if activity.id in parsed_activities:
                continue
            parsed_activities.add(activity.id)

            logger.info(f"Activity {activity.id} wasn't parsed yet, reading them …")
            shard = get_first_tiles(activity.id, repository, zoom)
            shard["activity_id"] = activity.id
            if not len(shard):
                continue
            tiles = pd.concat([tiles, shard])
    logger.info("Consolidating explorer tile history …")
    tiles = (
        tiles.sort_values("time")
        .groupby(["tile_x", "tile_y"])
        .apply(lambda group: group.iloc[0])
        .reset_index(drop=True)
    )

    logger.info("Store explorer tile history to cache file …")
    tiles.to_parquet(cache_file)

    return tiles
