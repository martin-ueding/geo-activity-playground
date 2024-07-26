import json
import logging
import pathlib
import shutil

import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.paths import activities_path
from geo_activity_playground.core.paths import activity_timeseries_dir
from geo_activity_playground.core.tasks import work_tracker_path

logger = logging.getLogger(__name__)


def delete_activities_per_tile() -> None:
    paths = [
        pathlib.Path("Cache/activities-per-tile.pickle"),
        pathlib.Path("Cache/activities-per-tile-task.json"),
    ]
    for path in paths:
        path.unlink(missing_ok=True)


def delete_work_tracker(name: str):
    work_tracker_path(name).unlink(missing_ok=True)


def reset_time_series_embellishment() -> None:
    pathlib.Path("Cache/work-tracker-embellish-time-series.pickle").unlink(
        missing_ok=True
    )


def delete_tile_visits() -> None:
    paths = [
        pathlib.Path("Cache/activities-per-tile.pickle"),
        pathlib.Path("Cache/tile-evolution-state.pickle"),
        pathlib.Path("Cache/tile-history.pickle"),
        pathlib.Path("Cache/tile-visits.pickle"),
        pathlib.Path("Cache/work-tracker-parse-activity-files.pickle"),
        pathlib.Path("Cache/work-tracker-tile-visits.pickle"),
    ]
    for path in paths:
        path.unlink(missing_ok=True)


def delete_heatmap_cache() -> None:
    path = pathlib.Path("Cache/Heatmap")
    if path.exists():
        shutil.rmtree(path)


def delete_activity_metadata() -> None:
    delete_work_tracker("parse-activity-files")
    activities_path().unlink(missing_ok=True)


def convert_distances_to_km() -> None:
    if activities_path().exists():
        activities = pd.read_parquet(activities_path())
        if not "distance_km" in activities.columns:
            activities["distance_km"] = activities["distance"] / 1000
        for col in ["distance", "distance/km"]:
            if col in activities.columns:
                del activities[col]
        activities.to_parquet(activities_path())

    for time_series_path in tqdm(
        list(activity_timeseries_dir().glob("*.parquet")),
        desc="Convert m to km",
    ):
        time_series = pd.read_parquet(time_series_path)
        if "distance" in time_series.columns:
            time_series["distance_km"] = time_series["distance"] / 1000
        for col in ["distance", "distance/km"]:
            if col in time_series.columns:
                del time_series[col]
        time_series.to_parquet(time_series_path)


def add_consider_for_achievements() -> None:
    activities_path = pathlib.Path("Cache/activities.parquet")
    if activities_path.exists():
        df = pd.read_parquet(activities_path)
        if "consider_for_achievements" not in df.columns:
            df["consider_for_achievements"] = True
        else:
            df.loc[
                df["consider_for_achievements"].isna(), "consider_for_achievements"
            ] = True
        df.to_parquet("Cache/activities.parquet")


def delete_everything() -> None:
    if pathlib.Path("Cache").exists():
        shutil.rmtree("Cache")


def apply_cache_migrations() -> None:
    logger.info("Apply cache migration if needed …")
    cache_status_file = pathlib.Path("Cache/status.json")
    if cache_status_file.exists():
        with open(cache_status_file) as f:
            cache_status = json.load(f)
    else:
        cache_status = {"num_applied_migrations": 0}

    migrations = [
        delete_activities_per_tile,
        reset_time_series_embellishment,
        delete_tile_visits,
        delete_heatmap_cache,
        delete_activity_metadata,
        delete_activity_metadata,
        convert_distances_to_km,
        delete_activity_metadata,
        delete_tile_visits,
        delete_heatmap_cache,
        add_consider_for_achievements,
        delete_tile_visits,
        delete_heatmap_cache,
        delete_tile_visits,
        delete_everything,
    ]

    for migration in migrations[cache_status["num_applied_migrations"] :]:
        logger.info(f"Applying cache migration {migration.__name__} …")
        migration()
        cache_status["num_applied_migrations"] += 1
        cache_status_file.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_status_file, "w") as f:
            json.dump(cache_status, f)
