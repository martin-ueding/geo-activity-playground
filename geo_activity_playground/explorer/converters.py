import collections
import datetime
import functools
import logging
import pathlib
import pickle
from typing import Any
from typing import Iterator

import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.core.tiles import interpolate_missing_tile


logger = logging.getLogger(__name__)

TILE_VISITS_PATH = pathlib.Path(f"Cache/tile-visits.pickle")


def tiles_from_points(
    time_series: pd.DataFrame, zoom: int
) -> Iterator[tuple[datetime.datetime, int, int]]:
    assert pd.api.types.is_dtype_equal(time_series["time"].dtype, "datetime64[ns, UTC]")
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
        yield (t1, int(x1), int(y1))
        # We don't want to interpolate over segment boundaries.
        if s1 == s2:
            interpolated = interpolate_missing_tile(x1, y1, x2, y2)
            if interpolated is not None:
                yield (t1,) + interpolated


@functools.cache
def load_tile_history() -> dict[int, dict[tuple[int, int], dict[str, Any]]]:
    with open(TILE_VISITS_PATH, "rb") as f:
        return pickle.load(f)


def compute_tile_visits(repository: ActivityRepository) -> None:
    if TILE_VISITS_PATH.exists():
        with open(TILE_VISITS_PATH, "rb") as f:
            tile_visits = pickle.load(f)
    else:
        tile_visits: dict[
            int, dict[tuple[int, int], dict[str, Any]]
        ] = collections.defaultdict(dict)

    work_tracker = WorkTracker("tile-visits")
    activity_ids_to_process = work_tracker.filter(repository.activity_ids)

    for activity_id in tqdm(activity_ids_to_process, desc="Extract explorer tiles"):
        time_series = repository.get_time_series(activity_id)
        for zoom in range(20):
            for time, tile_x, tile_y in tiles_from_points(time_series, zoom):
                tile = (tile_x, tile_y)
                if tile in tile_visits[zoom]:
                    d = tile_visits[zoom][tile]
                    d["count"] += 1
                    if d["first_time"] > time:
                        d["first_time"] = time
                        d["first_id"] = activity_id
                    if d["last_time"] < time:
                        d["last_time"] = time
                        d["last_id"] = activity_id
                    d["activity_ids"].add(activity_id)
                else:
                    tile_visits[zoom][tile] = {
                        "count": 1,
                        "first_time": time,
                        "first_id": activity_id,
                        "last_time": time,
                        "last_id": activity_id,
                        "activity_ids": {activity_id},
                    }
        work_tracker.mark_done(activity_id)

    logger.info("Store explorer tile history to cache file …")
    with open(TILE_VISITS_PATH, "wb") as f:
        pickle.dump(tile_visits, f)

    work_tracker.close()
