import collections
import datetime
import functools

import geojson
import matplotlib
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
            lambda group: sum(group["distance_km"])
        )
        monthly_distance.name = "total_distance_km"
        monthly_pivot = (
            monthly_distance.reset_index()
            .pivot(index="month", columns="year", values="total_distance_km")
            .fillna(0.0)
        )

        yearly_distance = meta.groupby(["year"]).apply(
            lambda group: sum(group["distance_km"])
        )
        yearly_distance.name = "total_distance_km"
        yearly_distances = {
            row["year"]: row["total_distance_km"]
            for index, row in yearly_distance.reset_index().iterrows()
        }

        return {
            "num_activities": len(self._repository.meta),
            "monthly_distances": monthly_pivot,
            "yearly_distances": yearly_distances,
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
        day_of_month = collections.defaultdict(dict)
        date = datetime.datetime(year, month, 1)
        while date.month == month:
            iso = date.isocalendar()
            weeks[iso.week][iso.weekday] = []
            day_of_month[iso.week][iso.weekday] = date.day
            date += datetime.timedelta(days=1)

        for index, row in filtered.iterrows():
            iso = row["start"].isocalendar()
            weeks[iso.week][iso.weekday].append(
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "distance_km": row["distance_km"],
                    "id": row["id"],
                }
            )

        return {
            "year": year,
            "month": month,
            "weeks": weeks,
            "day_of_month": day_of_month,
        }

    def render_day(self, year: int, month: int, day: int) -> dict:
        meta = self._repository.meta
        selection = meta["start"].dt.date == datetime.date(year, month, day)
        activities_that_day = meta.loc[selection]

        time_series = [
            self._repository.get_time_series(activity_id)
            for activity_id in activities_that_day["id"]
        ]

        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in ts.groupby("segment_id")
                        ]
                    ),
                    properties={"color": matplotlib.colors.to_hex(cmap(i % 8))},
                )
                for i, ts in enumerate(time_series)
            ]
        )

        activities_list = activities_that_day.to_dict(orient="records")
        for i, activity_record in enumerate(activities_list):
            activity_record["color"] = matplotlib.colors.to_hex(cmap(i % 8))

        return {
            "activities": activities_list,
            "geojson": geojson.dumps(fc),
            "date": datetime.date(year, month, day).isoformat(),
        }
