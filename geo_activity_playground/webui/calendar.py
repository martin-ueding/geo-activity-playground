import collections
import datetime
import functools

import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository


class CalendarController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render_overview(self) -> dict:
        meta = self._repository.meta.copy()
        meta["date"] = meta["start"].dt.date
        meta["year"] = meta["start"].dt.year
        meta["month"] = meta["start"].dt.month

        monthly_distance = meta.groupby(["year", "month"]).apply(
            lambda group: sum(group["distance"])
        )
        monthly_distance.name = "total_distance"
        monthly_pivot = (
            monthly_distance.reset_index()
            .pivot(index="month", columns="year", values="total_distance")
            .fillna(0.0)
        )

        return {
            "num_activities": len(self._repository.meta),
            "monthly_distances": monthly_pivot,
        }

    @functools.cache
    def render_month(self, year: int, month: int) -> dict:
        meta = self._repository.meta.copy()
        meta["date"] = meta["start"].dt.date
        meta["year"] = meta["start"].dt.year
        meta["month"] = meta["start"].dt.month
        meta["day"] = meta["start"].dt.day
        meta["day_of_week"] = meta["start"].dt.day_of_week
        meta["isoweek"] = meta["start"].dt.isocalendar().week

        filtered = meta.loc[
            (meta["year"] == year) & (meta["month"] == month)
        ].sort_values("start")

        weeks = collections.defaultdict(dict)

        date = datetime.datetime(year, month, 1)
        while date.month == month:
            iso = date.isocalendar()
            weeks[iso.week][iso.weekday] = []
            date += datetime.timedelta(days=1)

        for index, row in filtered.iterrows():
            iso = row["start"].isocalendar()
            weeks[iso.week][iso.weekday].append(
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "distance": row["distance"],
                    "id": row["id"],
                }
            )

        return {"year": year, "month": month, "weeks": weeks}
