import datetime
import logging
import time

import requests
import sqlalchemy as sa

from ...core.coordinates import get_distance
from ...core.datamodel import DB
from ...core.raster_map import USER_AGENT, GeoBounds
from ...core.tiles import compute_tile, get_tile_upper_left_lat_lon
from .model import (
    CHUNK_LENGTH_M,
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

_HIGHWAY_EXCLUDE = ("construction", "proposed", "razed", "abandoned")


def _build_overpass_query(bounds: GeoBounds) -> str:
    exclude = "|".join(_HIGHWAY_EXCLUDE)
    bbox = f"{bounds.lat_min},{bounds.lon_min},{bounds.lat_max},{bounds.lon_max}"
    return (
        "[out:json][timeout:60];"
        f'(way["highway"]["highway"!~"^({exclude})$"]({bbox}););'
        "out body;"
        ">;"
        "out skel qt;"
    )


def _fetch_overpass(bounds: GeoBounds) -> dict:
    response = requests.post(
        OVERPASS_URL,
        data={"data": _build_overpass_query(bounds)},
        headers={"User-Agent": USER_AGENT},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


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


def _store_ways(nodes: dict[int, tuple[float, float]], ways: list[dict]) -> None:
    way_osm_ids = [way["osm_id"] for way in ways]
    known_way_ids = {
        row[0]
        for row in DB.session.execute(
            sa.select(StreetWay.osm_id).where(StreetWay.osm_id.in_(way_osm_ids))
        )
    }
    known_node_ids = {
        row[0]
        for row in DB.session.execute(
            sa.select(StreetNode.osm_id).where(StreetNode.osm_id.in_(nodes))
        )
    }

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
            for seq, (lat1, lon1, lat2, lon2, length_m) in enumerate(
                subdivide_way(points)
            )
        )


def ensure_streets_for_bounds(bounds: GeoBounds) -> None:
    """Fetch and store street data for every not-yet-fetched region tile that
    overlaps `bounds`, querying Overpass one region tile at a time so that
    repeated activities in the same area don't re-trigger a fetch."""
    x_min, y_max = compute_tile(bounds.lat_min, bounds.lon_min, STREET_REGION_ZOOM)
    x_max, y_min = compute_tile(bounds.lat_max, bounds.lon_max, STREET_REGION_ZOOM)

    known_regions = {
        (row.tile_x, row.tile_y)
        for row in DB.session.execute(
            sa.select(StreetRegion.tile_x, StreetRegion.tile_y).where(
                StreetRegion.zoom == STREET_REGION_ZOOM
            )
        )
    }

    for tile_x in range(min(x_min, x_max), max(x_min, x_max) + 1):
        for tile_y in range(min(y_min, y_max), max(y_min, y_max) + 1):
            if (tile_x, tile_y) in known_regions:
                continue
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
