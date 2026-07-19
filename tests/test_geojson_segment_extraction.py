import pathlib

from geo_activity_playground.features.segments.matching import (
    extract_segment_from_geojson,
)


def test_extract_segment_from_geojson() -> None:
    geojson_str = pathlib.Path("tests/kp-niederkassler-straße.geojson").read_text()
    latlon = extract_segment_from_geojson(geojson_str)
    assert latlon[0] == [50.761744, 7.113486]
    assert latlon[-1] == [50.759869, 7.112859]
