import abc
import dataclasses
import datetime
from typing import Iterator

import pandas as pd


@dataclasses.dataclass
class Activity:
    id: int
    name: str
    kind: str
    equipment: str
    start: datetime.datetime
    distance: float
    duration: datetime.timedelta


class ActivityRepository(abc.ABC):
    @abc.abstractclassmethod
    def get_activity_by_id(id: int) -> Activity:
        raise NotImplementedError()

    @abc.abstractclassmethod
    def iter_activities() -> Iterator[Activity]:
        raise NotImplementedError()

    @abc.abstractclassmethod
    def get_time_series(id: int) -> pd.DataFrame:
        raise NotImplementedError()
