from .importing import read_gpx_activity

import pathlib


def test_gpx() -> None:
    activity = read_gpx_activity(pathlib.Path(__file__).parent / "2022-05-27_14-23_Fri.gpx")
    assert len(activity.track_points.columns) == 3

# def test_gzipped_gpx() -> None:
#     activity = read_gpx_activity(pathlib.Path(__file__).parent / "gzipped-gpx.gpx.gz")
#     assert len(activity.track_points.columns) == 3