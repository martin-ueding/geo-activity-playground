import json
import logging
import pathlib
import shutil

logger = logging.getLogger(__name__)


def delete_activities_per_tile() -> None:
    paths = [
        pathlib.Path("Cache/activities-per-tile.pickle"),
        pathlib.Path("Cache/activities-per-tile-task.json"),
    ]
    for path in paths:
        path.unlink(missing_ok=True)


def delete_work_tracker(name: str):
    def migration() -> None:
        path = pathlib.Path(f"Cache/work-tracker-{name}.pickle")
        path.unlink(missing_ok=True)

    return migration


def reset_time_series_embellishment() -> None:
    pathlib.Path("Cache/work-tracker-embellish-time-series.pickle").unlink(
        missing_ok=True
    )


def delete_tile_visits() -> None:
    paths = [
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
    ]

    for migration in migrations[cache_status["num_applied_migrations"] :]:
        logger.info(f"Applying cache migration {migration.__name__} …")
        migration()
        cache_status["num_applied_migrations"] += 1
        cache_status_file.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_status_file, "w") as f:
            json.dump(cache_status, f)
