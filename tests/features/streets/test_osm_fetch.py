import pytest

from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.raster_map import GeoBounds
from geo_activity_playground.features.streets.osm_fetch import (
    _build_overpass_query,
    _parse_overpass_response,
    subdivide_way,
)


def test_subdivide_way_produces_fixed_length_chunks_with_shorter_tail() -> None:
    points = [(52.0, 13.0), (52.0, 13.01)]
    total = get_distance(*points[0], *points[1])

    chunks = subdivide_way(points, chunk_length_m=20.0)

    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert chunk[4] == pytest.approx(20.0)
    assert chunks[-1][4] <= 20.0 + 1e-6
    assert sum(chunk[4] for chunk in chunks) == pytest.approx(total)


def test_subdivide_way_chunks_form_a_contiguous_chain() -> None:
    points = [(52.0, 13.0), (52.001, 13.0), (52.001, 13.002)]

    chunks = subdivide_way(points, chunk_length_m=20.0)

    assert chunks[0][0:2] == points[0]
    assert chunks[-1][2:4] == points[-1]
    for previous, current in zip(chunks, chunks[1:]):
        assert previous[2:4] == current[0:2]


def test_subdivide_way_shorter_than_chunk_length_yields_single_chunk() -> None:
    points = [(52.0, 13.0), (52.00001, 13.0)]

    chunks = subdivide_way(points, chunk_length_m=20.0)

    assert len(chunks) == 1
    assert chunks[0][0:2] == points[0]
    assert chunks[0][2:4] == points[1]


def test_subdivide_way_needs_at_least_two_points() -> None:
    assert subdivide_way([]) == []
    assert subdivide_way([(52.0, 13.0)]) == []


def test_subdivide_way_ignores_duplicate_points() -> None:
    assert subdivide_way([(52.0, 13.0), (52.0, 13.0)]) == []


def test_build_overpass_query_embeds_bbox_and_exclusions() -> None:
    bounds = GeoBounds(lat_min=52.0, lon_min=13.0, lat_max=52.1, lon_max=13.1)

    query = _build_overpass_query(bounds)

    assert "52.0,13.0,52.1,13.1" in query
    assert "construction" in query
    assert "proposed" in query


def test_parse_overpass_response_splits_nodes_and_ways() -> None:
    data = {
        "elements": [
            {"type": "node", "id": 1, "lat": 52.0, "lon": 13.0},
            {"type": "node", "id": 2, "lat": 52.001, "lon": 13.001},
            {
                "type": "way",
                "id": 100,
                "nodes": [1, 2],
                "tags": {"highway": "residential", "name": "Teststraße"},
            },
            {
                "type": "way",
                "id": 101,
                "nodes": [1, 2],
                "tags": {"highway": "footway"},
            },
        ]
    }

    nodes, ways = _parse_overpass_response(data)

    assert nodes == {1: (52.0, 13.0), 2: (52.001, 13.001)}
    assert ways == [
        {
            "osm_id": 100,
            "highway": "residential",
            "name": "Teststraße",
            "node_ids": [1, 2],
        },
        {
            "osm_id": 101,
            "highway": "footway",
            "name": None,
            "node_ids": [1, 2],
        },
    ]
