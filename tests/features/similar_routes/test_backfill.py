import datetime

import pandas as pd
import pytest
import sqlalchemy

from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.features.similar_routes.backfill import (
    RouteDistanceBackfill,
)
from geo_activity_playground.features.similar_routes.blueprint import (
    find_similar_routes,
)
from geo_activity_playground.features.similar_routes.model import RouteDistance


def add_activity(name: str, day: int, time_series: pd.DataFrame) -> int:
    activity = Activity(
        name=name,
        time_series_uuid=f"uuid-{name}",
        start=datetime.datetime(2026, 9, day, 12),
    )
    DB.session.add(activity)
    DB.session.commit()
    time_series.to_parquet(activity.time_series_path)
    return activity.id


def run_until_idle(task: RouteDistanceBackfill) -> None:
    for _ in range(100):
        if not task.run_step():
            return
    raise AssertionError("The backfill did not finish.")


def distances() -> dict[tuple[int, int], RouteDistance]:
    return {
        (row.activity_id, row.reference_activity_id): row
        for row in DB.session.scalars(sqlalchemy.select(RouteDistance))
    }


@pytest.fixture
def activities(app_context, road) -> dict[str, int]:
    return {
        "full": add_activity("full", 1, road(0, 2000, 5)),
        "partial": add_activity("partial", 2, road(500, 1500, 7)),
        "far": add_activity("far", 3, road(0, 2000, 5, north_m=10_000)),
    }


def test_backfill_compares_all_pairs_both_ways(activities: dict[str, int]) -> None:
    run_until_idle(RouteDistanceBackfill())

    rows = distances()
    assert len(rows) == 6
    assert rows[activities["partial"], activities["full"]].p100 < 1
    assert rows[activities["full"], activities["partial"]].p100 > 400
    assert rows[activities["far"], activities["full"]].p50 is None
    assert rows[activities["full"], activities["far"]].p50 is None


def test_backfill_picks_up_new_activities(activities: dict[str, int], road) -> None:
    task = RouteDistanceBackfill()
    run_until_idle(task)

    newest = add_activity("newest", 4, road(0, 2000, 11))
    run_until_idle(task)

    rows = distances()
    assert len(rows) == 12
    assert rows[newest, activities["full"]].p100 < 1


def test_similar_routes_respect_direction(activities: dict[str, int]) -> None:
    run_until_idle(RouteDistanceBackfill())

    def names(direction: str) -> list[str]:
        return [
            activity.name
            for activity, _ in find_similar_routes(
                activities["full"], "p95", direction, 100
            )
        ]

    assert names("min") == ["partial"]
    assert names("max") == []
    assert names("forward") == []
    assert names("backward") == ["partial"]


def test_deleting_an_activity_removes_its_distances(
    activities: dict[str, int],
) -> None:
    run_until_idle(RouteDistanceBackfill())

    DB.session.delete(DB.session.get(Activity, activities["partial"]))
    DB.session.commit()

    assert all(activities["partial"] not in pair for pair in distances())
    assert len(distances()) == 2


def test_page_renders_with_all_options(client, activities: dict[str, int]) -> None:
    run_until_idle(RouteDistanceBackfill())

    for direction in ["min", "max", "forward", "backward"]:
        response = client.get(
            f"/similar-routes/activity/{activities['full']}?quantile=p95&direction={direction}"
        )
        assert response.status_code == 200
