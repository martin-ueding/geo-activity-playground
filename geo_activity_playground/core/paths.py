"""
Paths within the playground and cache.
"""
import functools
import pathlib
import typing


def dir_wrapper(path: pathlib.Path) -> typing.Callable[[], pathlib.Path]:
    @functools.cache
    def wrapper() -> pathlib.Path:
        path.mkdir(exist_ok=True, parents=True)
        return path

    return wrapper


def file_wrapper(path: pathlib.Path) -> typing.Callable[[], pathlib.Path]:
    @functools.cache
    def wrapper() -> pathlib.Path:
        path.parent.mkdir(exist_ok=True, parents=True)
        return path

    return wrapper


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


cache_dir = dir_wrapper(_cache_dir)

activity_extracted_dir = dir_wrapper(_activity_extracted_dir)
activity_extracted_meta_dir = dir_wrapper(_activity_extracted_meta_dir)
activity_extracted_time_series_dir = dir_wrapper(_activity_extracted_time_series_dir)
activity_enriched_meta_dir = dir_wrapper(_activity_enriched_meta_dir)
activity_enriched_time_series_dir = dir_wrapper(_activity_enriched_time_series_dir)
tiles_per_time_series = dir_wrapper(_tiles_per_time_series)
strava_api_dir = dir_wrapper(_strava_api_dir)

activities_file = file_wrapper(_activities_file)
strava_dynamic_config_path = file_wrapper(_strava_dynamic_config_path)
