import abc
from typing import Iterator

import pandas as pd


class TimeSeriesSource(abc.ABC):
    @abc.abstractmethod
    def iter_activities(self) -> Iterator[pd.DataFrame]:
        ...
