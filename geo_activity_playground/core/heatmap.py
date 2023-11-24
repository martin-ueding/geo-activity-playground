import functools
import logging
import pathlib

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import work_tracker


logger = logging.getLogger(__name__)


@functools.cache
def get_all_points(repository: ActivityRepository) -> pd.DataFrame:
    logger.info("Gathering all points …")
    all_points_path = pathlib.Path("Cache/all_points.parquet")
    if all_points_path.exists():
        all_points = pd.read_parquet(all_points_path)
    else:
        all_points = pd.DataFrame()
    new_shards = []
    with work_tracker(pathlib.Path("Cache/task_all_points.json")) as tracker:
        for activity in repository.iter_activities():
            if activity.id in tracker:
                continue
            tracker.add(activity.id)

            logger.info(f"Parsing points from {activity.id} …")
            time_series = repository.get_time_series(activity.id)
            if len(time_series) == 0 or "latitude" not in time_series.columns:
                continue
            new_shards.append(time_series[["latitude", "longitude"]])
    logger.info("Concatenating shards …")
    all_points = pd.concat([all_points] + new_shards)
    all_points.to_parquet(all_points_path)
    return all_points
