import datetime
import logging
import time

import requests
import sqlalchemy as sa
from sqlalchemy.orm import Mapped

from ...core.coordinates import get_distance
from ...core.datamodel import DB
from ...core.raster_map import USER_AGENT, GeoBounds
from ...core.tiles import (
    compute_tile,
    compute_tile_float,
    get_tile_upper_left_lat_lon,
    interpolate_missing_tile,
)
from .model import (
    CHUNK_LENGTH_M,
    REGION_PADDING_DEG,
    SQL_IN_BATCH_SIZE,
    STREET_REGION_ZOOM,
    StreetChunk,
    StreetNode,
    StreetRegion,
    StreetWay,
)

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_REQUEST_DELAY_S = 1.0
"""Minimum time between requests to the public Overpass instance."""
OVERPASS_SERVER_TIMEOUT_S = 120
"""Server-side query budget. Dense urban region tiles (e.g. central Berlin
returns >45k ways for a single zoom-12 tile) can take over a minute to
process; the default 60 s risks a 504 from the reverse proxy."""
OVERPASS_MAX_RETRIES = 3
OVERPASS_RETRY_BACKOFF_S = 5.0

_HIGHWAY_EXCLUDE = ("construction", "proposed", "razed", "abandoned")
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


def _build_overpass_query(bounds: GeoBounds) -> str:
    exclude = "|".join(_HIGHWAY_EXCLUDE)
    bbox = f"{bounds.lat_min},{bounds.lon_min},{bounds.lat_max},{bounds.lon_max}"
    return (
        f"[out:json][timeout:{OVERPASS_SERVER_TIMEOUT_S}];"
        f'(way["highway"]["highway"!~"^({exclude})$"]({bbox}););'
        "out body;"
        ">;"
        "out skel qt;"
    )


def _fetch_overpass(bounds: GeoBounds) -> dict:
    query = _build_overpass_query(bounds)
    for attempt in range(1, OVERPASS_MAX_RETRIES + 1):
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=OVERPASS_SERVER_TIMEOUT_S + 30,
        )
        if (
            response.status_code in _RETRYABLE_STATUS_CODES
            and attempt < OVERPASS_MAX_RETRIES
        ):
            logger.warning(
                "Overpass request failed with %d (attempt %d/%d), retrying.",
                response.status_code,
                attempt,
                OVERPASS_MAX_RETRIES,
            )
            time.sleep(OVERPASS_RETRY_BACKOFF_S * attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise AssertionError("unreachable")  # pragma: no cover


def _parse_overpass_response(
    data: dict,
) -> tuple[dict[int, tuple[float, float]], list[dict]]:
    """Split raw Overpass elements into a node-id -> (lat, lon) map and a list
    of way records with their tags and referenced node ids."""
    nodes: dict[int, tuple[float, float]] = {}
    ways: list[dict] = []
    for element in data.get("elements", []):
        if element["type"] == "node":
            nodes[element["id"]] = (element["lat"], element["lon"])
        elif element["type"] == "way":
            tags = element.get("tags", {})
            ways.append(
                {
                    "osm_id": element["id"],
                    "highway": tags.get("highway", ""),
                    "name": tags.get("name"),
                    "node_ids": element["nodes"],
                }
            )
    return nodes, ways


def subdivide_way(
    points: list[tuple[float, float]], chunk_length_m: float = CHUNK_LENGTH_M
) -> list[tuple[float, float, float, float, float]]:
    """Cut a way's polyline into pieces of roughly `chunk_length_m`.

    The final piece may be shorter. Returns a list of
    `(lat1, lon1, lat2, lon2, length_m)` tuples, in order along the way.
    """
    if len(points) < 2:
        return []

    cumulative = [0.0]
    for previous, current in zip(points, points[1:]):
        cumulative.append(
            cumulative[-1]
            + get_distance(previous[0], previous[1], current[0], current[1])
        )
    total = cumulative[-1]
    if total <= 0:
        return []

    def point_at(distance: float) -> tuple[float, float]:
        for i in range(1, len(cumulative)):
            if cumulative[i] >= distance:
                seg_start, seg_end = cumulative[i - 1], cumulative[i]
                if seg_end == seg_start:
                    return points[i]
                frac = (distance - seg_start) / (seg_end - seg_start)
                lat = points[i - 1][0] + frac * (points[i][0] - points[i - 1][0])
                lon = points[i - 1][1] + frac * (points[i][1] - points[i - 1][1])
                return (lat, lon)
        return points[-1]

    chunks: list[tuple[float, float, float, float, float]] = []
    prev_point = points[0]
    prev_dist = 0.0
    dist = chunk_length_m
    while dist < total:
        point = point_at(dist)
        chunks.append((*prev_point, *point, dist - prev_dist))
        prev_point = point
        prev_dist = dist
        dist += chunk_length_m
    if total - prev_dist > 1e-6:
        chunks.append((*prev_point, *points[-1], total - prev_dist))
    return chunks


def _existing_osm_ids(column: Mapped[int], osm_ids: list[int]) -> set[int]:
    found: set[int] = set()
    for i in range(0, len(osm_ids), SQL_IN_BATCH_SIZE):
        batch = osm_ids[i : i + SQL_IN_BATCH_SIZE]
        found.update(
            row[0]
            for row in DB.session.execute(sa.select(column).where(column.in_(batch)))
        )
    return found


def _store_ways(nodes: dict[int, tuple[float, float]], ways: list[dict]) -> None:
    known_way_ids = _existing_osm_ids(StreetWay.osm_id, [way["osm_id"] for way in ways])
    known_node_ids = _existing_osm_ids(StreetNode.osm_id, list(nodes))

    new_node_ids = set(nodes) - known_node_ids
    if new_node_ids:
        DB.session.add_all(
            StreetNode(osm_id=osm_id, lat=nodes[osm_id][0], lon=nodes[osm_id][1])
            for osm_id in new_node_ids
        )

    for way in ways:
        if way["osm_id"] in known_way_ids:
            continue
        points = [nodes[node_id] for node_id in way["node_ids"] if node_id in nodes]
        if len(points) < 2:
            continue
        street_way = StreetWay(
            osm_id=way["osm_id"], highway=way["highway"], name=way["name"]
        )
        DB.session.add(street_way)
        DB.session.flush()

        # Chunks are cut per original node-to-node edge, not across the whole
        # polyline, so that every chunk boundary that coincides with a real
        # OSM node keeps that node's exact (lat, lon) as its endpoint. That
        # lets the map-matching graph builder unify intersections purely by
        # comparing chunk-endpoint coordinates, without separate topology
        # bookkeeping.
        edge_chunks = [
            piece for a, b in zip(points, points[1:]) for piece in subdivide_way([a, b])
        ]
        DB.session.add_all(
            StreetChunk(
                way_id=street_way.id,
                seq=seq,
                lat1=lat1,
                lon1=lon1,
                lat2=lat2,
                lon2=lon2,
                length_m=length_m,
            )
            for seq, (lat1, lon1, lat2, lon2, length_m) in enumerate(edge_chunks)
        )


def _region_tiles_for_path(
    latitudes: list[float], longitudes: list[float]
) -> set[tuple[int, int]]:
    """Region tiles (at `STREET_REGION_ZOOM`) that an activity's track
    actually passes through, with a small padding so streets just off the
    recorded track are still covered.

    Deliberately does *not* use the track's bounding box: a long, mostly
    linear activity (a car trip, a point-to-point hike) can have a bounding
    box that is mostly empty countryside far from the actual route, which
    would blow up both the number of Overpass queries and the amount of
    irrelevant street data fetched and stored.
    """
    tiles: set[tuple[int, int]] = set()
    for lat, lon in zip(latitudes, longitudes):
        for pad_lat, pad_lon in (
            (0.0, 0.0),
            (REGION_PADDING_DEG, 0.0),
            (-REGION_PADDING_DEG, 0.0),
            (0.0, REGION_PADDING_DEG),
            (0.0, -REGION_PADDING_DEG),
        ):
            tiles.add(compute_tile(lat + pad_lat, lon + pad_lon, STREET_REGION_ZOOM))

    # Fill in diagonal gaps between consecutive points, the same way explorer
    # tiles do, so a fast-moving diagonal track doesn't skip a tile it passed
    # through the corner of.
    for (lat1, lon1), (lat2, lon2) in zip(
        zip(latitudes, longitudes), zip(latitudes[1:], longitudes[1:])
    ):
        x1, y1 = compute_tile_float(lat1, lon1, STREET_REGION_ZOOM)
        x2, y2 = compute_tile_float(lat2, lon2, STREET_REGION_ZOOM)
        interpolated = interpolate_missing_tile(x1, y1, x2, y2)
        if interpolated is not None:
            tiles.add(interpolated)

    return tiles


def ensure_streets_for_path(latitudes: list[float], longitudes: list[float]) -> None:
    """Fetch and store street data for every not-yet-fetched region tile
    along an activity's track, querying Overpass one region tile at a time so
    that repeated activities in the same area don't re-trigger a fetch."""
    tiles = _region_tiles_for_path(latitudes, longitudes)
    if not tiles:
        return

    known_regions = {
        (row.tile_x, row.tile_y)
        for row in DB.session.execute(
            sa.select(StreetRegion.tile_x, StreetRegion.tile_y).where(
                StreetRegion.zoom == STREET_REGION_ZOOM
            )
        )
    }

    for tile_x, tile_y in sorted(tiles - known_regions):
        _fetch_region(tile_x, tile_y)


def _fetch_region(tile_x: int, tile_y: int) -> None:
    lat_max, lon_min = get_tile_upper_left_lat_lon(tile_x, tile_y, STREET_REGION_ZOOM)
    lat_min, lon_max = get_tile_upper_left_lat_lon(
        tile_x + 1, tile_y + 1, STREET_REGION_ZOOM
    )
    region_bounds = GeoBounds(
        lat_min=lat_min, lon_min=lon_min, lat_max=lat_max, lon_max=lon_max
    )

    logger.info("Fetching street data for region tile (%d, %d).", tile_x, tile_y)
    data = _fetch_overpass(region_bounds)
    nodes, ways = _parse_overpass_response(data)
    _store_ways(nodes, ways)
    DB.session.add(
        StreetRegion(
            zoom=STREET_REGION_ZOOM,
            tile_x=tile_x,
            tile_y=tile_y,
            fetched_at=datetime.datetime.now(),
        )
    )
    DB.session.commit()
    time.sleep(OVERPASS_REQUEST_DELAY_S)
