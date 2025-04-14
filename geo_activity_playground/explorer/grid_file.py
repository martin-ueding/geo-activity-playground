import json
import logging
from collections.abc import Iterable
from typing import Optional

import geojson
import gpxpy
import pandas as pd

from ..core.coordinates import Bounds
from ..core.tiles import get_tile_upper_left_lat_lon


logger = logging.getLogger(__name__)


def get_border_tiles(
    tiles: pd.DataFrame, zoom: int, tile_bounds: Bounds
) -> list[list[tuple[float, float]]]:
    logger.info("Generate border tiles …")
    tile_set = set(zip(tiles["tile_x"], tiles["tile_y"]))
    border_tiles = set()
    for tile_x in range(tile_bounds.x_min, tile_bounds.x_max):
        for tile_y in range(tile_bounds.y_min, tile_bounds.y_max):
            tile = (tile_x, tile_y)
            if tile not in tile_set:
                border_tiles.add(tile)
    return make_grid_points(border_tiles, zoom)


def get_explored_tiles(
    tiles: pd.DataFrame, zoom: int
) -> list[list[tuple[float, float]]]:
    return make_grid_points(zip(tiles["tile_x"], tiles["tile_y"]), zoom)


def make_explorer_tile(
    tile_x: int, tile_y: int, properties: dict, zoom: int
) -> geojson.Feature:
    return make_explorer_rectangle(
        tile_x, tile_y, tile_x + 1, tile_y + 1, zoom, properties
    )


def make_explorer_rectangle(
    x1: int, y1: int, x2: int, y2: int, zoom: int, properties: Optional[dict] = None
) -> geojson.Feature:
    corners = [
        get_tile_upper_left_lat_lon(*args)
        for args in [
            (x1, y1, zoom),
            (x2, y1, zoom),
            (x2, y2, zoom),
            (x1, y2, zoom),
            (x1, y1, zoom),
        ]
    ]
    try:
        json.dumps(properties)
    except TypeError:
        logger.error(f"Cannot serialize the following as JSON: {properties}")
        raise
    return geojson.Feature(
        geometry=geojson.Polygon([[(coord[1], coord[0]) for coord in corners]]),
        properties=properties,
    )


def make_grid_points(
    tiles: Iterable[tuple[int, int]], zoom: int
) -> list[list[tuple[float, float]]]:
    result = []
    for tile_x, tile_y in tiles:
        tile = [
            get_tile_upper_left_lat_lon(tile_x, tile_y, zoom),
            get_tile_upper_left_lat_lon(tile_x + 1, tile_y, zoom),
            get_tile_upper_left_lat_lon(tile_x + 1, tile_y + 1, zoom),
            get_tile_upper_left_lat_lon(tile_x, tile_y + 1, zoom),
            get_tile_upper_left_lat_lon(tile_x, tile_y, zoom),
        ]
        result.append(tile)
    return result


def make_grid_file_gpx(grid_points: list[list[tuple[float, float]]]) -> str:
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    for points in grid_points:
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        for point in points:
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*point))
    return gpx.to_xml()


def make_grid_file_geojson(grid_points: list[list[tuple[float, float]]]) -> str:
    fc = geojson.FeatureCollection(
        [
            geojson.Feature(
                geometry=geojson.Polygon([[[lon, lat] for lat, lon in points]])
            )
            for points in grid_points
        ]
    )
    result = geojson.dumps(fc, sort_keys=True, indent=4, ensure_ascii=False)
    return result
