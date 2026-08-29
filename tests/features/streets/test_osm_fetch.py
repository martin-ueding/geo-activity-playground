from unittest.mock import patch

import pytest
import requests
import sqlalchemy as sa

from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.datamodel import DB
from geo_activity_playground.core.raster_map import GeoBounds
from geo_activity_playground.core.tiles import compute_tile
from geo_activity_playground.features.streets.model import (
    STREET_REGION_ZOOM,
    StreetChunk,
    StreetWay,
)
from geo_activity_playground.features.streets.osm_fetch import (
    _build_overpass_query,
    _fetch_overpass,
    _parse_overpass_response,
    _region_tiles_for_path,
    _store_ways,
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


def test_store_ways_chunk_boundaries_land_exactly_on_real_nodes(
    app_context: None,
) -> None:
    # Each edge is long enough to require more than one ~20 m chunk, so the
    # subdivision must cross a chunk boundary while still landing exactly on
    # node B -- otherwise a way sharing that intersection node would not be
    # connected to this one in the map-matching graph.
    node_a = (52.0, 13.0)
    node_b = (52.0, 13.0003)
    node_c = (52.0, 13.0006)
    nodes = {1: node_a, 2: node_b, 3: node_c}
    ways = [
        {"osm_id": 100, "highway": "residential", "name": None, "node_ids": [1, 2, 3]}
    ]

    _store_ways(nodes, ways)
    DB.session.flush()

    way = DB.session.scalars(sa.select(StreetWay)).one()
    chunks = DB.session.scalars(
        sa.select(StreetChunk)
        .where(StreetChunk.way_id == way.id)
        .order_by(StreetChunk.seq)
    ).all()

    endpoints = {(chunks[0].lat1, chunks[0].lon1)}
    for chunk in chunks:
        endpoints.add((chunk.lat2, chunk.lon2))

    assert node_a in endpoints
    assert node_b in endpoints
    assert node_c in endpoints
    assert len(chunks) > 2


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def test_fetch_overpass_retries_on_gateway_timeout() -> None:
    bounds = GeoBounds(lat_min=52.0, lon_min=13.0, lat_max=52.1, lon_max=13.1)
    responses = [
        _FakeResponse(504),
        _FakeResponse(200, {"elements": []}),
    ]

    with (
        patch("time.sleep"),
        patch(
            "geo_activity_playground.features.streets.osm_fetch.requests.post",
            side_effect=responses,
        ) as mock_post,
    ):
        result = _fetch_overpass(bounds)

    assert result == {"elements": []}
    assert mock_post.call_count == 2


def test_fetch_overpass_gives_up_after_max_retries() -> None:
    bounds = GeoBounds(lat_min=52.0, lon_min=13.0, lat_max=52.1, lon_max=13.1)
    responses = [_FakeResponse(504) for _ in range(5)]

    with (
        patch("time.sleep"),
        patch(
            "geo_activity_playground.features.streets.osm_fetch.requests.post",
            side_effect=responses,
        ) as mock_post,
    ):
        with pytest.raises(requests.exceptions.HTTPError):
            _fetch_overpass(bounds)

    assert mock_post.call_count == 3


def test_region_tiles_for_path_stays_close_to_a_long_linear_route() -> None:
    # Sankt Augustin to Oldenburg: a long, mostly-diagonal car trip whose
    # bounding box is mostly empty countryside. Region-tile selection must
    # follow the path, not the bounding box, or this blows up into hundreds
    # of tiles covering irrelevant land.
    lat1, lon1 = 50.77, 7.17
    lat2, lon2 = 53.14, 8.21
    n = 500
    latitudes = [lat1 + (lat2 - lat1) * i / (n - 1) for i in range(n)]
    longitudes = [lon1 + (lon2 - lon1) * i / (n - 1) for i in range(n)]

    tiles = _region_tiles_for_path(latitudes, longitudes)

    x1, y1 = compute_tile(lat1, lon1, STREET_REGION_ZOOM)
    x2, y2 = compute_tile(lat2, lon2, STREET_REGION_ZOOM)
    bbox_tile_count = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1)

    # The straight-line distance is ~264 km; at ~1.5 km per zoom-14 tile that
    # is on the order of ~180 tiles along the path, not the ~500x more tiles
    # the bounding box would cover.
    assert len(tiles) < bbox_tile_count / 10
    assert len(tiles) < 400


def test_region_tiles_for_path_includes_padded_neighbors() -> None:
    lat, lon = 52.0, 13.0
    tile = compute_tile(lat, lon, STREET_REGION_ZOOM)

    tiles = _region_tiles_for_path([lat], [lon])

    assert tile in tiles
    assert len(tiles) >= 1


def test_region_tiles_for_path_fills_diagonal_gap() -> None:
    # Two points placed in diagonally adjacent tiles (100, 100) and
    # (101, 99), far enough from the tile edges that padding alone would not
    # bridge them, must still include the connecting corner tile -- mirroring
    # how explorer tiles handle diagonal jumps (core.tiles.interpolate_missing_tile).
    from geo_activity_playground.core.tiles import xy_to_latlon

    lat1, lon1 = xy_to_latlon(100.9, 100.9, STREET_REGION_ZOOM)
    lat2, lon2 = xy_to_latlon(101.1, 99.5, STREET_REGION_ZOOM)

    tiles = _region_tiles_for_path([lat1, lat2], [lon1, lon2])

    assert (100, 100) in tiles
    assert (101, 99) in tiles
    assert (101, 100) in tiles
