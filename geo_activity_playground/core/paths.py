"""
Paths within the playground and cache.
"""
import functools
import pathlib
import typing


def make_path(path) -> typing.Callable[[], pathlib.Path]:
    @functools.cache
    def path_creator() -> pathlib.Path:
        path.mkdir(exist_ok=True, parents=True)
        return path

    return path_creator


cache_dir = make_path(pathlib.Path("Cache"))
activity_timeseries_dir = make_path(cache_dir / "Activity Timeseries")

activities_path = lambda: cache_dir() / "activities.parquet"


def activity_timeseries_path(activity_id: int) -> pathlib.Path:
    return activity_timeseries_dir() / f"{activity_id}.parquet"
