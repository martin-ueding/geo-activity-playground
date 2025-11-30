import pathlib

from geo_activity_playground.core.segments import extract_segment_from_geojson


def test_extract_segment_from_geojson() -> None:
    geojson_str = pathlib.Path("tests/kp-niederkassler-straße.geojson").read_text()
    latlon = extract_segment_from_geojson(geojson_str)
    assert latlon[0] == (7.113486, 50.761744)
    assert latlon[-1] == (7.112859, 50.759869)
