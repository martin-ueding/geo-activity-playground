import abc
import pathlib
from typing import Iterator

import pandas as pd

from .activity_parsers import read_activity


class TimeSeriesSource(abc.ABC):
    @abc.abstractmethod
    def iter_activities(self) -> Iterator[pd.DataFrame]:
        ...


class DirectoryTimeSeriesSource(TimeSeriesSource):
    def iter_activities(self) -> Iterator[pd.DataFrame]:
        activity_dir = pathlib.Path.cwd() / "Activities"
        for path in activity_dir.rglob("*.*"):
            df = read_activity(path)
            # Some FIT files don't have any location data, they might be just weight lifting. We'll skip them.
            if len(df) == 0:
                continue
            yield df
