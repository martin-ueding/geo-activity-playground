import geojson


def extract_segment_from_geojson(geojson_str: str) -> list[tuple[float, float]]:
    gj = geojson.loads(geojson_str)
    coordinates = gj["features"][0]["geometry"]["coordinates"]
    return [(c[1], c[0]) for c in coordinates]
