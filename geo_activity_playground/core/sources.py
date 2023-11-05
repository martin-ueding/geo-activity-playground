import abc
import pathlib
from typing import Iterator

import pandas as pd


class TimeSeriesSource(abc.ABC):
    @abc.abstractmethod
    def iter_activities(self) -> Iterator[pd.DataFrame]:
        ...


class DirectoryTimeSeriesSource(TimeSeriesSource):
    def iter_activities(self) -> Iterator[pd.DataFrame]:
        activity_dir = pathlib.Path.cwd() / "Activities"
