import json

import numpy as np
import pandas as pd

from geo_activity_playground.core.activities import (
    make_geojson_from_time_series,
    make_track_feature,
)


def test_track_feature_has_one_line_per_segment() -> None:
    time_series = pd.DataFrame(
        {
            "latitude": [50.0, 50.1, np.nan, 50.2, 51.0, 51.1, 52.0],
            "longitude": [7.0, 7.1, 7.15, 7.2, 8.0, 8.1, 9.0],
            "segment_id": [0, 0, 0, 0, 1, 1, 2],
        }
    )
    feature = make_track_feature(time_series, color="#ff0000")

    assert feature is not None
    assert feature["geometry"]["type"] == "MultiLineString"
    assert feature["geometry"]["coordinates"] == [
        [[7.0, 50.0], [7.1, 50.1], [7.2, 50.2]],
        [[8.0, 51.0], [8.1, 51.1]],
    ]
    assert feature["properties"] == {"color": "#ff0000"}


def test_track_feature_without_drawable_line() -> None:
    assert make_track_feature(pd.DataFrame({"time": [1, 2]})) is None
    assert (
        make_track_feature(pd.DataFrame({"latitude": [50.0], "longitude": [7.0]}))
        is None
    )


def test_line_geojson_has_no_points() -> None:
    time_series = pd.DataFrame(
        {
            "latitude": np.linspace(50, 51, 10),
            "longitude": np.linspace(7, 8, 10),
            "distance_km": np.linspace(0, 100, 10),
            "segment_id": 0,
        }
    )
    collection = json.loads(make_geojson_from_time_series(time_series))

    assert [f["geometry"]["type"] for f in collection["features"]] == [
        "MultiLineString"
    ]
    assert json.loads(make_geojson_from_time_series(time_series.iloc[:0])) == {
        "type": "FeatureCollection",
        "features": [],
    }
