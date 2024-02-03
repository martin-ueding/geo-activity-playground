"""
Paths within the playground and cache.
"""
import functools
import pathlib
import typing


def dir_wrapper(
    dir_func: typing.Callable[[], pathlib.Path]
) -> typing.Callable[[], pathlib.Path]:
    @functools.wraps(dir_func)
    @functools.cache
    def wrapper() -> pathlib.Path:
        path = dir_func()
        path.mkdir(exist_ok=True, parents=True)
        return path

    return wrapper


@dir_wrapper
def cache_dir() -> pathlib.Path:
    return pathlib.Path("Cache")


@dir_wrapper
def activity_timeseries_dir() -> pathlib.Path:
    return cache_dir() / "Activity Timeseries"


def activities_path() -> pathlib.Path:
    return cache_dir() / "activities.parquet"


def activity_timeseries_path(activity_id: int) -> pathlib.Path:
    return activity_timeseries_dir() / f"{activity_id}.parquet"
