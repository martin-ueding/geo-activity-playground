from xml.etree import ElementTree as ET

from .grid_file import make_grid_file_kml_squadrats

KML_NS = "{http://www.opengis.net/kml/2.2}"


def _placemarks(kml: str) -> dict[str, ET.Element]:
    root = ET.fromstring(kml)
    return {pm.findtext(f"{KML_NS}name"): pm for pm in root.iter(f"{KML_NS}Placemark")}


def test_squadrats_kml_has_all_four_placemarks() -> None:
    kml = make_grid_file_kml_squadrats(
        explored={14: [(8000, 5000)], 17: [(64000, 40000)]},
        squares={14: (8000, 5000, 3), 17: (64000, 40000, 2)},
    )
    placemarks = _placemarks(kml)
    assert set(placemarks) == {
        "squadrats",
        "squadratinhos",
        "ubersquadrat",
        "ubersquadratinho",
    }


def test_squadrats_size_is_tile_count_and_polygons_match() -> None:
    kml = make_grid_file_kml_squadrats(
        explored={14: [(8000, 5000), (8001, 5000)]},
        squares={},
    )
    placemark = _placemarks(kml)["squadrats"]
    size = placemark.find(
        f"{KML_NS}ExtendedData/{KML_NS}Data[@name='size']/{KML_NS}value"
    )
    assert size.text == "2"
    polygons = placemark.findall(f"{KML_NS}MultiGeometry/{KML_NS}Polygon")
    assert len(polygons) == 2


def test_square_size_is_side_length_and_single_polygon() -> None:
    kml = make_grid_file_kml_squadrats(
        explored={14: [(8000, 5000)]},
        squares={14: (8000, 5000, 42)},
    )
    placemark = _placemarks(kml)["ubersquadrat"]
    size = placemark.find(
        f"{KML_NS}ExtendedData/{KML_NS}Data[@name='size']/{KML_NS}value"
    )
    assert size.text == "42"
    assert placemark.find(f"{KML_NS}MultiGeometry") is None
    assert placemark.find(f"{KML_NS}Polygon") is not None


def test_missing_zoom_and_zero_square_are_skipped() -> None:
    kml = make_grid_file_kml_squadrats(
        explored={14: [(8000, 5000)]},
        squares={14: (8000, 5000, 0)},
    )
    assert set(_placemarks(kml)) == {"squadrats"}


def test_coordinates_are_lon_lat() -> None:
    kml = make_grid_file_kml_squadrats(explored={14: [(8000, 5000)]}, squares={})
    coordinates = (
        _placemarks(kml)["squadrats"]
        .find(
            f"{KML_NS}MultiGeometry/{KML_NS}Polygon/{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates"
        )
        .text
    )
    first_lon, first_lat = (float(v) for v in coordinates.split()[0].split(","))
    assert -180 <= first_lon <= 180
    assert -90 <= first_lat <= 90
