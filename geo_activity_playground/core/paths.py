import contextlib
import functools
import pathlib
import typing

import appdirs

"""
Paths within the playground and cache.
"""

APPDIRS = appdirs.AppDirs(appname="Geo Activity Playground", appauthor="Martin Ueding")

USER_CACHE_DIR = pathlib.Path(APPDIRS.user_cache_dir)
USER_CONFIG_DIR = pathlib.Path(APPDIRS.user_config_dir)
USER_DATA_DIR = pathlib.Path(APPDIRS.user_data_dir)


def dir_wrapper(path: pathlib.Path) -> typing.Callable[[], pathlib.Path]:
    def wrapper() -> pathlib.Path:
        path.mkdir(exist_ok=True, parents=True)
        return path

    return wrapper


def file_wrapper(path: pathlib.Path) -> typing.Callable[[], pathlib.Path]:
    def wrapper() -> pathlib.Path:
        path.parent.mkdir(exist_ok=True, parents=True)
        return path

    return wrapper


@contextlib.contextmanager
def atomic_open(path: pathlib.Path, mode: str):
    temp_path = path.with_stem(path.stem + "-temp")
    with open(temp_path, mode) as f:
        yield f
    path.unlink(missing_ok=True)
    temp_path.rename(path)


_cache_dir = pathlib.Path("Cache")

_activity_dir = _cache_dir / "Activity"
_activity_extracted_dir = _activity_dir / "Extracted"
_activity_extracted_meta_dir = _activity_extracted_dir / "Meta"
_activity_extracted_time_series_dir = _activity_extracted_dir / "Time Series"

_activity_enriched_dir = _activity_dir / "Enriched"
_activity_enriched_meta_dir = _activity_enriched_dir / "Meta"
_activity_enriched_time_series_dir = _activity_enriched_dir / "Time Series"
_activities_file = _activity_dir / "activities.parquet"

_tiles_per_time_series = _cache_dir / "Tiles" / "Tiles Per Time Series"

_strava_api_dir = pathlib.Path("Strava API")
_strava_dynamic_config_path = _strava_api_dir / "strava-client-id.json"
_strava_last_activity_date_path = _cache_dir / "strava-last-activity-date.json"
_new_config_file = pathlib.Path("config.json")
_activity_meta_override_dir = pathlib.Path("Metadata Override")
_time_series_dir = pathlib.Path("Time Series")
_photos_dir = pathlib.Path("Photos")


cache_dir = dir_wrapper(_cache_dir)
activity_extracted_dir = dir_wrapper(_activity_extracted_dir)
activity_extracted_meta_dir = dir_wrapper(_activity_extracted_meta_dir)
activity_extracted_time_series_dir = dir_wrapper(_activity_extracted_time_series_dir)
activity_enriched_meta_dir = dir_wrapper(_activity_enriched_meta_dir)
activity_enriched_time_series_dir = dir_wrapper(_activity_enriched_time_series_dir)
tiles_per_time_series = dir_wrapper(_tiles_per_time_series)
strava_api_dir = dir_wrapper(_strava_api_dir)
activity_meta_override_dir = dir_wrapper(_activity_meta_override_dir)
TIME_SERIES_DIR = dir_wrapper(_time_series_dir)
PHOTOS_DIR = dir_wrapper(_photos_dir)

activities_file = file_wrapper(_activities_file)
strava_dynamic_config_path = file_wrapper(_strava_dynamic_config_path)
strava_last_activity_date_path = file_wrapper(_strava_last_activity_date_path)
new_config_file = file_wrapper(_new_config_file)
