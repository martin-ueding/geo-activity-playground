import functools
import logging
import pathlib
import pickle

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import work_tracker
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
        time_series = repository.get_time_series(id)
        tiles = tiles_from_points(time_series, zoom)
        first_tiles = first_time_per_tile(tiles)
        target_path.parent.mkdir(exist_ok=True, parents=True)
        first_tiles.to_parquet(target_path)
        return first_tiles


def tiles_from_points(time_series: pd.DataFrame, zoom: int) -> pd.DataFrame:
    assert pd.api.types.is_dtype_equal(time_series["time"].dtype, "datetime64[ns, UTC]")
    new_rows = []
    if "latitude" in time_series.columns and "longitude" in time_series.columns:
        xf = time_series["x"] * 2**zoom
        yf = time_series["y"] * 2**zoom
        for t1, x1, y1, x2, y2, s1, s2 in zip(
            time_series["time"],
            xf,
            yf,
            xf.shift(1),
            yf.shift(1),
            time_series["segment_id"],
            time_series["segment_id"].shift(1),
        ):
            # We don't want to interpolate over segment boundaries.
            if s1 != s2:
                continue
            new_rows.append((t1, int(x1), int(y1)))
            if len(new_rows) > 1:
                interpolated = interpolate_missing_tile(x1, y1, x2, y2)
                if interpolated is not None:
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

    cache_file = pathlib.Path(f"Cache/first_time_per_tile_{zoom}.pickle")

    if cache_file.exists():
        with open(cache_file, "rb") as f:
            tile_visits = pickle.load(f)
    else:
        tile_visits = {}

    with work_tracker(
        pathlib.Path(f"Cache/task_first_time_per_tile_{zoom}_v2.json")
    ) as parsed_activities:
        for activity in repository.iter_activities(new_to_old=False):
            if activity.id in parsed_activities:
                continue
            parsed_activities.add(activity.id)

            logger.info(f"Activity {activity.id} wasn't parsed yet, reading them …")
            shard = get_first_tiles(activity.id, repository, zoom)
            if not len(shard):
                continue
            for _, row in shard.iterrows():
                tile = (row["tile_x"], row["tile_y"])
                if tile in tile_visits:
                    d = tile_visits[tile]
                    d["count"] += 1
                    if d["first_time"] > row["time"]:
                        d["first_time"] = row["time"]
                        d["first_id"] = activity.id
                    if d["last_time"] < row["time"]:
                        d["last_time"] = row["time"]
                        d["last_id"] = activity.id
                else:
                    tile_visits[tile] = {
                        "count": 1,
                        "first_time": row["time"],
                        "first_id": activity.id,
                        "last_time": row["time"],
                        "last_id": activity.id,
                    }

    logger.info("Store explorer tile history to cache file …")
    with open(cache_file, "wb") as f:
        pickle.dump(tile_visits, f)

    tiles = pd.DataFrame(
        [{"tile_x": x, "tile_y": y, **meta} for (x, y), meta in tile_visits.items()]
    )
    parquet_output = pathlib.Path(f"Cache/first_time_per_tile_{zoom}.parquet")
    tiles.to_parquet(parquet_output)
    return tiles
