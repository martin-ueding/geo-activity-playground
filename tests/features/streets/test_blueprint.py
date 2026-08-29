from flask import Flask
from flask.testing import FlaskClient

from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.features.streets.model import (
    StreetChunk,
    StreetChunkVisit,
    StreetWay,
)


def _add_way_with_chunks(app: Flask) -> None:
    with app.app_context():
        way = StreetWay(osm_id=1, highway="residential", name="Teststraße")
        DB.session.add(way)
        DB.session.flush()

        visited_chunk = StreetChunk(
            way_id=way.id,
            seq=0,
            lat1=52.0,
            lon1=13.0,
            lat2=52.0,
            lon2=13.001,
            length_m=20,
        )
        unvisited_chunk = StreetChunk(
            way_id=way.id,
            seq=1,
            lat1=52.0,
            lon1=13.001,
            lat2=52.0,
            lon2=13.002,
            length_m=20,
        )
        DB.session.add_all([visited_chunk, unvisited_chunk])
        DB.session.flush()

        activity = Activity(id=1, name="Ride")
        DB.session.add(activity)
        DB.session.flush()
        DB.session.add(
            StreetChunkVisit(
                chunk_id=visited_chunk.id,
                first_activity_id=activity.id,
                last_activity_id=activity.id,
                visit_count=1,
            )
        )
        DB.session.commit()


def test_streets_geojson_marks_visited_and_unvisited_chunks(
    app: Flask, client: FlaskClient
) -> None:
    _add_way_with_chunks(app)

    response = client.get("/streets/geojson?south=51.9&west=12.9&north=52.1&east=13.1")

    assert response.status_code == 200
    data = response.get_json()
    assert data["type"] == "FeatureCollection"
    visited_flags = sorted(
        feature["properties"]["visited"] for feature in data["features"]
    )
    assert visited_flags == [False, True]


def test_streets_geojson_requires_bbox_params(client: FlaskClient) -> None:
    response = client.get("/streets/geojson")
    assert response.status_code == 400
