import functools
import logging
import pathlib

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import work_tracker
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.core.tiles import interpolate_missing_tile


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
    if "latitude" in points.columns and "longitude" in points.columns:
        xf, yf = compute_tile_float(points["latitude"], points["longitude"], zoom)
        for t1, x1, y1, x2, y2 in zip(points["time"], xf, yf, xf.shift(1), yf.shift(1)):
            new_rows.append((t1, int(x1), int(y1)))
            if len(new_rows) > 1:
                interpolated = interpolate_missing_tile(x1, y1, x2, y2)
                if interpolated is not None:
                    logger.info(
                        f"Interpolated an explorer tile: {(x1, y1)}, {(x2, y2)} → {interpolated}"
                    )
                    new_rows.append((t1,) + interpolated)
    return pd.DataFrame(new_rows, columns=["time", "tile_x", "tile_y"])


def first_time_per_tile(tiles: pd.DataFrame) -> pd.DataFrame:
    reduced = tiles.groupby(["tile_x", "tile_y"]).min().reset_index()
    return reduced


def reduce_tile_group(group: pd.DataFrame) -> pd.DataFrame:
    first_idx = group["first_time"].argmin()
    last_idx = group["last_time"].argmax()
    return pd.DataFrame(
        {
            "first_time": group["first_time"].iloc[first_idx],
            "first_id": group["first_id"].iloc[first_idx],
            "last_time": group["last_time"].iloc[last_idx],
            "last_id": group["last_id"].iloc[last_idx],
            "count": group["count"].sum(),
        },
        index=[0],
    )


@functools.cache
def get_tile_history(repository: ActivityRepository, zoom: int) -> pd.DataFrame:
    logger.info("Building explorer tile history from all activities …")

    cache_file = pathlib.Path(f"Cache/first_time_per_tile_{zoom}.parquet")
    if cache_file.exists():
        tiles = pd.read_parquet(cache_file)
    else:
        tiles = pd.DataFrame()

    len_tiles_before = len(tiles)
    with work_tracker(
        pathlib.Path(f"Cache/task_first_time_per_tile_{zoom}.json")
    ) as parsed_activities:
        for activity in repository.iter_activities(new_to_old=False):
            if activity.id in parsed_activities:
                continue
            parsed_activities.add(activity.id)

            logger.info(f"Activity {activity.id} wasn't parsed yet, reading them …")
            shard = get_first_tiles(activity.id, repository, zoom)
            if not len(shard):
                continue
            shard2 = pd.DataFrame(
                {
                    "tile_x": shard["tile_x"],
                    "tile_y": shard["tile_y"],
                    "first_id": activity.id,
                    "last_id": activity.id,
                    "first_time": shard["time"],
                    "last_time": shard["time"],
                    "count": 1,
                }
            )
            tiles = pd.concat([tiles, shard2])
    if len(tiles) != len_tiles_before:
        logger.info("Consolidating explorer tile history …")
        tiles = (
            tiles.groupby(["tile_x", "tile_y"]).apply(reduce_tile_group).reset_index()
        )

        logger.info("Store explorer tile history to cache file …")
        tiles.to_parquet(cache_file)

    return tiles
