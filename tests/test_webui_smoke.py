"""
Smoke tests for web UI routes.

These tests verify that routes load without crashing.
They don't check for correctness, just that pages render with HTTP 200.
"""

import datetime as dt
import re

import pandas as pd

from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Equipment,
    Kind,
    TileVisit,
)
from geo_activity_playground.core.tile_visits import get_tile_history_df
from geo_activity_playground.features.explorer.clustering import (
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
    assert b'id="wrap-month-selector"' in response.data


def test_explorer_style_json_loads(client):
    response = client.get("/explorer/14/style.json")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert "sources" in data
    assert "layers" in data
    assert "gap-explorer-14-colorful_cluster" in data["sources"]
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_explorer_style_json_with_color_strategy(client):
    response = client.get("/explorer/14/style.json?color_strategy=max_cluster")
    assert response.status_code == 200
    data = response.get_json()
    assert "gap-explorer-14-max_cluster" in data["sources"]


def test_explorer_latest_new_tiles_isolates_latest_activity(client, app):
    import io

    import numpy as np
    from PIL import Image

    with app.app_context():
        DB.session.add_all([Activity(id=1, name="Old"), Activity(id=2, name="New")])
        DB.session.add_all(
            [
                TileVisit(
                    zoom=14,
                    tile_x=100,
                    tile_y=200,
                    first_activity_id=1,
                    first_time=dt.datetime(2025, 1, 1),
                    last_activity_id=1,
                    last_time=dt.datetime(2025, 1, 1),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=101,
                    tile_y=200,
                    first_activity_id=2,
                    first_time=dt.datetime(2026, 8, 1),
                    last_activity_id=2,
                    last_time=dt.datetime(2026, 8, 1),
                    visit_count=1,
                ),
            ]
        )
        DB.session.commit()

    def tile_array(tile_x, tile_y, query=""):
        response = client.get(
            f"/explorer/14/tile/14/{tile_x}/{tile_y}.png?color_strategy=latest_new{query}"
        )
        assert response.status_code == 200
        return np.asarray(Image.open(io.BytesIO(response.data)).convert("RGBA"))

    # Only the tile first explored by the latest activity (id=2) is highlighted, and
    # the highlight is a border so that neighbouring tiles cannot overlap.
    latest = tile_array(101, 200)
    assert int(latest[2, 128, 3]) > 0
    assert int(latest[128, 128, 3]) == 0
    assert int(tile_array(100, 200)[2, 128, 3]) == 0

    # An explicit activity selects that activity instead of the latest one.
    assert int(tile_array(100, 200, "&activity_id=1")[2, 128, 3]) > 0
    assert int(tile_array(101, 200, "&activity_id=1")[2, 128, 3]) == 0


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


def test_wrap_month_uses_activity_local_timezone_for_new_tiles(client, app):
    with app.app_context():
        kind = Kind(name="Ride")
        equipment = Equipment(name="Bike")
        DB.session.add_all([kind, equipment])
        DB.session.flush()
        DB.session.add(
            Activity(
                id=1,
                name="Midnight Ride",
                start=dt.datetime(2025, 12, 31, 23, 30, 0),
                iana_timezone="Europe/Berlin",
                distance_km=10.0,
                elevation_gain=100.0,
                moving_time=dt.timedelta(minutes=30),
                elapsed_time=dt.timedelta(minutes=30),
                kind_id=kind.id,
                equipment_id=equipment.id,
            )
        )
        DB.session.add(
            TileVisit(
                zoom=14,
                tile_x=0,
                tile_y=0,
                first_activity_id=1,
                first_time=dt.datetime(2025, 12, 31, 23, 30, 0),
                last_activity_id=1,
                last_time=dt.datetime(2025, 12, 31, 23, 30, 0),
                visit_count=1,
            )
        )
        DB.session.commit()

    response = client.get("/calendar/wrap/2026/1")
    assert response.status_code == 200
    html = response.data.decode()
    match = re.search(
        r"New Tiles \(z14\)</div>\s*<div class=\"display-6 fw-semibold\">(\d+)</div>",
        html,
    )
    assert match is not None
    assert match.group(1) == "1"


def test_activity_page_shows_tile_changes(client, app):
    with app.app_context():
        kind = Kind(name="Ride")
        equipment = Equipment(name="Bike")
        DB.session.add_all([kind, equipment])
        DB.session.flush()
        activity = Activity(
            id=1,
            name="Ride",
            start=dt.datetime(2026, 1, 1, 10, 0, 0),
            iana_timezone="UTC",
            distance_km=1.0,
            elevation_gain=0.0,
            moving_time=dt.timedelta(minutes=10),
            elapsed_time=dt.timedelta(minutes=10),
            kind_id=kind.id,
            equipment_id=equipment.id,
        )
        DB.session.add(activity)
        DB.session.add(
            TileVisit(
                zoom=14,
                tile_x=8000,
                tile_y=5000,
                first_activity_id=1,
                first_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                last_activity_id=1,
                last_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                visit_count=1,
            )
        )
        DB.session.commit()
        time_series = pd.DataFrame(
            {
                "time": pd.to_datetime(
                    [
                        dt.datetime(2026, 1, 1, 10, 0, 0),
                        dt.datetime(2026, 1, 1, 10, 5, 0),
                    ]
                ).tz_localize("UTC"),
                "latitude": [50.0, 50.01],
                "longitude": [7.0, 7.01],
                "distance_km": [0.0, 1.0],
                "segment_id": [0, 0],
                "speed": [10.0, 12.0],
                "elevation": [100.0, 110.0],
            }
        )
        path = activity.time_series_path
        path.parent.mkdir(parents=True, exist_ok=True)
        time_series.to_parquet(path)

    response = client.get("/activity/1")
    assert response.status_code == 200
    assert b"New explorer tiles" in response.data
    assert b"New Tiles & Cluster Growth" in response.data
    assert b"data-bounds-geojson" in response.data
    assert b"Newly discovered" in response.data


def test_color_strategy_settings_round_trip(client, app):
    response = client.get("/settings/color-strategy")
    assert response.status_code == 200
    assert b"color_strategy_new_tile_color" in response.data
    assert b"color_strategy_new_cluster_color" in response.data

    response = client.post(
        "/settings/color-strategy",
        data={
            "color_strategy_max_cluster_color": "#377eb8",
            "color_strategy_max_cluster_color_alpha": "77",
            "color_strategy_max_cluster_other_color": "#4daf4a",
            "color_strategy_max_cluster_other_color_alpha": "77",
            "color_strategy_visited_color": "#000000",
            "color_strategy_visited_color_alpha": "77",
            "color_strategy_new_tile_color": "#ff0000",
            "color_strategy_new_tile_color_alpha": "255",
            "color_strategy_new_cluster_color": "#0066ff",
            "color_strategy_new_cluster_color_alpha": "255",
            "cmap_opacity": "0.5",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        from geo_activity_playground.core.datamodel import UiConfig

        assert DB.session.get(UiConfig, 1).color_strategy_new_tile_color == "#ff0000ff"
