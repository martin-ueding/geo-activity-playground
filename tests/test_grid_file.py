from xml.etree import ElementTree as ET

from geo_activity_playground.explorer.grid_file import (
    make_grid_file_kml,
    make_grid_file_osm,
    make_grid_points,
)


def _example_points() -> list[list[tuple[float, float]]]:
    return make_grid_points([(8508, 5471), (8509, 5471)], zoom=14)


def test_make_grid_file_kml_has_one_polygon_per_tile() -> None:
    kml = make_grid_file_kml(_example_points())
    assert kml.count("<Polygon") == 2


def test_make_grid_file_osm_is_well_formed_with_one_way_per_tile() -> None:
    osm = ET.fromstring(make_grid_file_osm(_example_points()))
    ways = osm.findall("way")
    assert len(ways) == 2
    # Each tile is a square with four distinct corners plus a closing reference.
    assert all(len(way.findall("nd")) == 5 for way in ways)
    assert len(osm.findall("node")) == 8
