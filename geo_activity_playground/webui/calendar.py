import functools

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
