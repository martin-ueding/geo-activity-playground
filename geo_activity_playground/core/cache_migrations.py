import json
import logging
import pathlib

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
        delete_work_tracker("embellish-time-series"),
    ]

    for migration in migrations[cache_status["num_applied_migrations"] :]:
        logger.info(f"Applying cache migration {migration.__name__} …")
        migration()
        cache_status["num_applied_migrations"] += 1
        cache_status_file.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_status_file, "w") as f:
            json.dump(cache_status, f)
