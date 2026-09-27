"""The aggregate map on the search map page must not silently drop tracks."""

import datetime
import uuid

import pandas as pd
from flask import Flask

from geo_activity_playground.core.datamodel import DB, Activity, Equipment, Kind


def _add_kind_and_equipment() -> tuple[Kind, Equipment]:
    equipment = Equipment(name="Bike")
    kind = Kind(name="Ride")
    DB.session.add_all([equipment, kind])
    DB.session.flush()
    return kind, equipment


def _add_activity(
    name: str,
    start: datetime.datetime,
    segments: int,
    kind: Kind,
    equipment: Equipment,
) -> Activity:
    activity = Activity(
        name=name,
        start=start,
        distance_km=85.0,
        elapsed_time=datetime.timedelta(hours=3),
        moving_time=datetime.timedelta(hours=3),
        kind=kind,
        equipment=equipment,
        time_series_uuid=str(uuid.uuid4()),
    )
    DB.session.add(activity)
    DB.session.flush()
    activity.replace_time_series(
        pd.DataFrame(
            {
                "time": [
                    start + datetime.timedelta(minutes=i) for i in range(2 * segments)
                ],
                "latitude": [51.0 + 0.001 * i for i in range(2 * segments)],
                "longitude": [3.0 + 0.001 * i for i in range(2 * segments)],
                "segment_id": [i // 2 for i in range(2 * segments)],
            }
        )
    )
    return activity


def test_aggregate_geojson_covers_every_activity(app: Flask) -> None:
    """Multi-segment activities used to exhaust a line budget shared with the
    activity cap, which dropped whole tracks off the end of the map."""
    with app.app_context():
        kind, equipment = _add_kind_and_equipment()
        base = datetime.datetime(2026, 1, 1, 10, 0, 0)
        expected = set()
        for i in range(60):
            activity = _add_activity(
                f"Ride {i}", base + datetime.timedelta(days=i), 3, kind, equipment
            )
            expected.add(activity.id)
        DB.session.commit()

    response = app.test_client().get("/search/map/aggregate.geojson")
    assert response.status_code == 200
    features = response.get_json()["features"]

    assert {feature["properties"]["activity_id"] for feature in features} == expected
    assert len(features) == 60
    assert all(len(feature["geometry"]["coordinates"]) == 3 for feature in features)


def test_aggregate_geojson_keeps_newest_first_within_cap(app: Flask) -> None:
    with app.app_context():
        kind, equipment = _add_kind_and_equipment()
        base = datetime.datetime(2026, 1, 1, 10, 0, 0)
        for i in range(120):
            _add_activity(
                f"Ride {i}", base + datetime.timedelta(days=i), 1, kind, equipment
            )
        DB.session.commit()

    response = app.test_client().get("/search/map/aggregate.geojson")
    features = response.get_json()["features"]

    assert [feature["properties"]["activity_name"] for feature in features] == [
        f"Ride {i}" for i in range(119, 19, -1)
    ]
