import functools
import pathlib
from typing import Iterator

import pandas as pd

from ..core.activity_parsers import read_activity
from ..core.sources import TimeSeriesSource


@functools.cache
def activity_cache_dir() -> pathlib.Path:
    activity_cache_dir = pathlib.Path.cwd() / "Strava Export Cache" / "Activities"
    activity_cache_dir.mkdir(exist_ok=True, parents=True)
    return activity_cache_dir


def make_activity_cache_path(activity_path: pathlib.Path) -> pathlib.Path:
    return activity_cache_dir() / (activity_path.stem.split(".")[0] + ".parquet")


class StravaExportTimeSeriesSource(TimeSeriesSource):
    def iter_activities(self) -> Iterator[pd.DataFrame]:
        activity_paths = list(
            (pathlib.Path("Strava Export") / "activities").glob("?????*.*")
        )
        activity_paths.sort()
        for path in activity_paths:
            df = read_activity(path)
            # Some FIT files don't have any location data, they might be just weight lifting. We'll skip them.
            if len(df) == 0:
                continue
            yield df
