import dataclasses
import datetime
from typing import Iterator

import geojson
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
        return f"{self.name} ({self.kind}; {self.distance:.1f} km; {self.elapsed_time})"


class ActivityRepository:
    def __init__(self) -> None:
        self.meta = pd.read_parquet("Cache/activities.parquet")
        self.meta.index = self.meta["id"]
        self.meta.index.name = "index"
        self.meta["distance"] /= 1000

    def iter_activities(self, new_to_old=True) -> Iterator[ActivityMeta]:
        direction = -1 if new_to_old else 1
        for id, row in self.meta[::direction].iterrows():
            yield ActivityMeta(**row)

    def get_activity_by_id(self, id: int) -> ActivityMeta:
        return ActivityMeta(**self.meta.loc[id])

    def get_time_series(self, id: int) -> pd.DataFrame:
        df = pd.read_parquet(f"Cache/Activity Timeseries/{id}.parquet")
        df.name = id
        if pd.api.types.is_dtype_equal(df["time"].dtype, "int64"):
            start = self.get_activity_by_id(id).start
            time = df["time"]
            del df["time"]
            df["time"] = [start + datetime.timedelta(seconds=t) for t in time]
        assert pd.api.types.is_dtype_equal(df["time"].dtype, "datetime64[ns, UTC]")
        return df


def make_geojson_from_time_series(time_series: pd.DataFrame) -> str:
    line = geojson.LineString(
        [
            (lon, lat)
            for lat, lon in zip(time_series["latitude"], time_series["longitude"])
        ]
    )
    return geojson.dumps(line)
