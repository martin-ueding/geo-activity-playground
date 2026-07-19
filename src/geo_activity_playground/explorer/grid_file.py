import json
import logging
from collections.abc import Iterable
from xml.etree import ElementTree as ET

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
    x1: int, y1: int, x2: int, y2: int, zoom: int, properties: dict | None = None
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


def make_grid_file_kml(grid_points: list[list[tuple[float, float]]]) -> str:
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(kml, "Document")
    for points in grid_points:
        placemark = ET.SubElement(document, "Placemark")
        _add_squadrats_polygon(placemark, points)
    return ET.tostring(kml, encoding="unicode")


# The Squadrats KML uses four named placemarks: explored tiles at zoom 14
# (squadrats) and 17 (squadratinhos), plus the largest square at each zoom level
# (ubersquadrat, ubersquadratinho). Colors are KML's aabbggrr hex strings.
_SQUADRATS_TILE_LAYERS = {
    14: {
        "name": "squadrats",
        "poly_color": "40FFFFFF",
        "line_color": "FF808080",
        "line_width": "1",
    },
    17: {
        "name": "squadratinhos",
        "poly_color": "400085FF",
        "line_color": "FF000000",
        "line_width": "0.25",
    },
}
_SQUADRATS_SQUARE_LAYERS = {
    14: {"name": "ubersquadrat", "line_color": "FF0000FF", "line_width": "2"},
    17: {"name": "ubersquadratinho", "line_color": "FF00477A", "line_width": "1"},
}


def _add_squadrats_extended_data(placemark: ET.Element, name: str, size: int) -> None:
    extended_data = ET.SubElement(placemark, "ExtendedData")
    name_data = ET.SubElement(extended_data, "Data", name="name")
    ET.SubElement(name_data, "value").text = name
    size_data = ET.SubElement(extended_data, "Data", name="size")
    ET.SubElement(size_data, "value").text = str(size)


def _add_squadrats_polygon(parent: ET.Element, ring: list[tuple[float, float]]) -> None:
    polygon = ET.SubElement(parent, "Polygon")
    outer = ET.SubElement(polygon, "outerBoundaryIs")
    linear_ring = ET.SubElement(outer, "LinearRing")
    ET.SubElement(linear_ring, "coordinates").text = " ".join(
        f"{lon},{lat}" for lat, lon in ring
    )


def make_grid_file_kml_squadrats(
    explored: dict[int, Iterable[tuple[int, int]]],
    squares: dict[int, tuple[int, int, int]],
) -> str:
    """Build a Squadrats-compatible KML for the Explorer Tile Helper app.

    Args:
        explored: Explored tiles per zoom level, keyed by 14 and/or 17.
        squares: Largest square as ``(x, y, size)`` per zoom level.
    """
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(kml, "Document")

    for zoom, spec in _SQUADRATS_TILE_LAYERS.items():
        tiles = list(explored.get(zoom, []))
        if not tiles:
            continue
        placemark = ET.SubElement(document, "Placemark")
        ET.SubElement(placemark, "name").text = spec["name"]
        style = ET.SubElement(placemark, "Style")
        ET.SubElement(ET.SubElement(style, "PolyStyle"), "color").text = spec[
            "poly_color"
        ]
        line_style = ET.SubElement(style, "LineStyle")
        ET.SubElement(line_style, "color").text = spec["line_color"]
        ET.SubElement(line_style, "width").text = spec["line_width"]
        _add_squadrats_extended_data(placemark, spec["name"], len(tiles))
        multi_geometry = ET.SubElement(placemark, "MultiGeometry")
        for ring in make_grid_points(tiles, zoom):
            _add_squadrats_polygon(multi_geometry, ring)

    for zoom, spec in _SQUADRATS_SQUARE_LAYERS.items():
        square = squares.get(zoom)
        if square is None or square[2] == 0:
            continue
        x, y, size = square
        placemark = ET.SubElement(document, "Placemark")
        ET.SubElement(placemark, "name").text = spec["name"]
        style = ET.SubElement(placemark, "Style")
        ET.SubElement(ET.SubElement(style, "PolyStyle"), "fill").text = "0"
        line_style = ET.SubElement(style, "LineStyle")
        ET.SubElement(line_style, "color").text = spec["line_color"]
        ET.SubElement(line_style, "width").text = spec["line_width"]
        _add_squadrats_extended_data(placemark, spec["name"], size)
        corners = [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]
        ring = [get_tile_upper_left_lat_lon(cx, cy, zoom) for cx, cy in corners]
        _add_squadrats_polygon(placemark, ring)

    return ET.tostring(kml, encoding="unicode")


def make_grid_file_osm(grid_points: list[list[tuple[float, float]]]) -> str:
    osm = ET.Element("osm", version="0.6", generator="geo-activity-playground")
    node_id = -1
    way_id = -1
    for points in grid_points:
        way_node_ids = []
        # The rings from make_grid_points repeat the first point as the last one;
        # mkgmap closes ways by repeating the node reference, so drop the duplicate.
        for lat, lon in points[:-1]:
            ET.SubElement(osm, "node", id=str(node_id), lat=repr(lat), lon=repr(lon))
            way_node_ids.append(node_id)
            node_id -= 1
        way = ET.SubElement(osm, "way", id=str(way_id))
        for ref in [*way_node_ids, way_node_ids[0]]:
            ET.SubElement(way, "nd", ref=str(ref))
        ET.SubElement(way, "tag", k="boundary", v="administrative")
        ET.SubElement(way, "tag", k="admin_level", v="2")
        way_id -= 1
    return ET.tostring(osm, encoding="unicode")
