"""
Smoke tests for web UI routes.

These tests verify that routes load without crashing.
They don't check for correctness, just that pages render with HTTP 200.
"""

import datetime as dt
import re

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


def test_wrap_uses_cluster_activation_time_for_new_cluster_tiles(client, app):
    with app.app_context():
        kind = Kind(name="Ride")
        equipment = Equipment(name="Bike")
        DB.session.add_all([kind, equipment])
        DB.session.flush()
        DB.session.add_all(
            [
                Activity(
                    id=1,
                    name="Center Early",
                    start=dt.datetime(2025, 6, 1, 10, 0, 0),
                    iana_timezone="UTC",
                    distance_km=1.0,
                    elevation_gain=0.0,
                    moving_time=dt.timedelta(minutes=10),
                    elapsed_time=dt.timedelta(minutes=10),
                    kind_id=kind.id,
                    equipment_id=equipment.id,
                ),
                Activity(
                    id=2,
                    name="West",
                    start=dt.datetime(2026, 1, 1, 10, 0, 0),
                    iana_timezone="UTC",
                    distance_km=1.0,
                    elevation_gain=0.0,
                    moving_time=dt.timedelta(minutes=10),
                    elapsed_time=dt.timedelta(minutes=10),
                    kind_id=kind.id,
                    equipment_id=equipment.id,
                ),
                Activity(
                    id=3,
                    name="North",
                    start=dt.datetime(2026, 1, 1, 10, 1, 0),
                    iana_timezone="UTC",
                    distance_km=1.0,
                    elevation_gain=0.0,
                    moving_time=dt.timedelta(minutes=10),
                    elapsed_time=dt.timedelta(minutes=10),
                    kind_id=kind.id,
                    equipment_id=equipment.id,
                ),
                Activity(
                    id=4,
                    name="South",
                    start=dt.datetime(2026, 1, 1, 10, 2, 0),
                    iana_timezone="UTC",
                    distance_km=1.0,
                    elevation_gain=0.0,
                    moving_time=dt.timedelta(minutes=10),
                    elapsed_time=dt.timedelta(minutes=10),
                    kind_id=kind.id,
                    equipment_id=equipment.id,
                ),
                Activity(
                    id=5,
                    name="East",
                    start=dt.datetime(2026, 1, 1, 10, 3, 0),
                    iana_timezone="UTC",
                    distance_km=1.0,
                    elevation_gain=0.0,
                    moving_time=dt.timedelta(minutes=10),
                    elapsed_time=dt.timedelta(minutes=10),
                    kind_id=kind.id,
                    equipment_id=equipment.id,
                ),
            ]
        )
        DB.session.add_all(
            [
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=0,
                    first_activity_id=1,
                    first_time=dt.datetime(2025, 6, 1, 10, 0, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2025, 6, 1, 10, 0, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=-1,
                    tile_y=0,
                    first_activity_id=2,
                    first_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                    last_activity_id=2,
                    last_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=-1,
                    first_activity_id=3,
                    first_time=dt.datetime(2026, 1, 1, 10, 1, 0),
                    last_activity_id=3,
                    last_time=dt.datetime(2026, 1, 1, 10, 1, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=1,
                    first_activity_id=4,
                    first_time=dt.datetime(2026, 1, 1, 10, 2, 0),
                    last_activity_id=4,
                    last_time=dt.datetime(2026, 1, 1, 10, 2, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=1,
                    tile_y=0,
                    first_activity_id=5,
                    first_time=dt.datetime(2026, 1, 1, 10, 3, 0),
                    last_activity_id=5,
                    last_time=dt.datetime(2026, 1, 1, 10, 3, 0),
                    visit_count=1,
                ),
            ]
        )
        DB.session.commit()
        rebuild_cluster_history_for_zoom(14, get_tile_history_df(14))

    year_response = client.get("/calendar/wrap/2026")
    assert year_response.status_code == 200
    year_html = year_response.data.decode()
    year_match = re.search(
        r"New Cluster Tiles \(z14\)</div>\s*<div class=\"display-6 fw-semibold\">(\d+)</div>",
        year_html,
    )
    assert year_match is not None
    assert year_match.group(1) == "1"

    month_response = client.get("/calendar/wrap/2026/1")
    assert month_response.status_code == 200
    month_html = month_response.data.decode()
    month_match = re.search(
        r"New Cluster Tiles \(z14\)</div>\s*<div class=\"display-6 fw-semibold\">(\d+)</div>",
        month_html,
    )
    assert month_match is not None
    assert month_match.group(1) == "1"
