import abc
import dataclasses
import datetime
from typing import Iterator
from typing import Optional

import pandas as pd


@dataclasses.dataclass
class ActivityMeta:
    calories: float
    commute: bool
    distance: float
    elapsed_time: datetime.timedelta
    equipment: str
    id: int
    kind: str
    name: str
    start: datetime.datetime

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}; {self.distance/1000:.1f} km; {self.elapsed_time})"


class ActivityRepository(abc.ABC):
    @abc.abstractmethod
    def iter_activities(self) -> Iterator[ActivityMeta]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_activity_by_id(self, id: int) -> ActivityMeta:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_time_series(self, id: int) -> pd.DataFrame:
        raise NotImplementedError()
