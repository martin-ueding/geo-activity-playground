"""
Smoke tests for web UI routes.

These tests verify that routes load without crashing.
They don't check for correctness, just that pages render with HTTP 200.
"""

import datetime as dt

from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Equipment,
    Kind,
    TileVisit,
)
from geo_activity_playground.explorer.tile_visits import (
    get_tile_history_df,
    rebuild_cluster_history_for_zoom,
)


def test_home_page_loads(client):
    """Test that the home page loads with an empty database."""
    response = client.get("/")
    assert response.status_code == 200
    # Verify it's actually HTML content
    assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data


def test_wrap_latest_page_loads_without_data(client):
    response = client.get("/calendar/wrap")
    assert response.status_code == 200
    assert b"Year Wrap" in response.data


def test_wrap_year_page_loads_without_data(client):
    response = client.get("/calendar/wrap/2026")
    assert response.status_code == 200
    assert b"Year Wrap" in response.data


def test_wrap_month_page_loads_without_data(client):
    response = client.get("/calendar/wrap/2026/1")
    assert response.status_code == 200
    assert b"Month Wrap" in response.data


def test_wrap_month_page_loads_with_data(client, app):
    with app.app_context():
        kind = Kind(name="Ride")
        equipment = Equipment(name="Bike")
        DB.session.add(kind)
        DB.session.add(equipment)
        DB.session.flush()
        activity = Activity(
            id=1,
            name="Morning Ride",
            start=dt.datetime(2026, 1, 15, 7, 0, 0),
            iana_timezone="UTC",
            distance_km=42.0,
            elevation_gain=500.0,
            moving_time=dt.timedelta(hours=2, minutes=10),
            elapsed_time=dt.timedelta(hours=2, minutes=20),
            kind_id=kind.id,
            equipment_id=equipment.id,
        )
        DB.session.add(activity)
        DB.session.commit()

    response = client.get("/calendar/wrap/2026/1")
    assert response.status_code == 200
    assert b"Month Wrap 2026-01" in response.data


def test_cluster_history_endpoints_load(client, app):
    with app.app_context():
        activity = Activity(id=1, name="Ride")
        DB.session.add(activity)
        DB.session.add(
            TileVisit(
                zoom=14,
                tile_x=100,
                tile_y=200,
                first_activity_id=1,
                first_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                last_activity_id=1,
                last_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                visit_count=1,
            )
        )
        DB.session.commit()
        rebuild_cluster_history_for_zoom(14, get_tile_history_df(14))

    snapshot = client.get("/explorer/14/cluster-history/snapshot.geojson?event_index=1")
    assert snapshot.status_code == 200
    assert snapshot.is_json

    diff = client.get("/explorer/14/cluster-history/activity/1/diff.geojson")
    assert diff.status_code == 200
    assert diff.is_json
