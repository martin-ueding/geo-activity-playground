import pathlib

import gpxpy
import numpy as np
import scipy.ndimage

from ..core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.core.sources import TimeSeriesSource
from geo_activity_playground.explorer.converters import get_tile_history


def get_border_tiles(ts_source: TimeSeriesSource):
    tiles = get_tile_history(ts_source)
    a = np.zeros((2**14, 2**14), dtype=np.int8)
    a[tiles["tile_x"], tiles["tile_y"]] = 1
    dilated = scipy.ndimage.binary_dilation(a, iterations=1)
    border = dilated - a
    border_x, border_y = np.where(border)
    return border_x, border_y


def make_adapted_grid_file(border_x, border_y):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    for tile_x, tile_y in zip(border_x, border_y):
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y, 14))
        )
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(
                *get_tile_upper_left_lat_lon(tile_x + 1, tile_y, 14)
            )
        )
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(
                *get_tile_upper_left_lat_lon(tile_x + 1, tile_y + 1, 14)
            )
        )
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(
                *get_tile_upper_left_lat_lon(tile_x, tile_y + 1, 14)
            )
        )
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y, 14))
        )

    out_path = pathlib.Path("Explorer") / "missing_tiles.gpx"
    out_path.parent.mkdir(exist_ok=True, parents=True)

    with open(out_path, "w") as f:
        f.write(gpx.to_xml())
