import pathlib
from typing import Iterator

import geojson
import gpxpy
import numpy as np
import scipy.ndimage

from ..core.sources import TimeSeriesSource
from ..core.tiles import get_tile_upper_left_lat_lon
from .converters import get_tile_history


def get_border_tiles(ts_source: TimeSeriesSource) -> list[list[list[float]]]:
    tiles = get_tile_history(ts_source)
    a = np.zeros((2**14, 2**14), dtype=np.int8)
    a[tiles["tile_x"], tiles["tile_y"]] = 1
    dilated = scipy.ndimage.binary_dilation(a, iterations=1)
    border = dilated - a
    border_x, border_y = np.where(border)
    return make_grid_points(zip(border_x, border_y))


def get_explored_tiles(ts_source: TimeSeriesSource) -> list[list[list[float]]]:
    tiles = get_tile_history(ts_source)
    return make_grid_points(zip(tiles["tile_x"], tiles["tile_y"]))


def make_grid_points(
    tile_iterator: Iterator[tuple[int, int]]
) -> list[list[list[float]]]:
    result = []
    for tile_x, tile_y in tile_iterator:
        tile = [
            get_tile_upper_left_lat_lon(tile_x, tile_y, 14),
            get_tile_upper_left_lat_lon(tile_x + 1, tile_y, 14),
            get_tile_upper_left_lat_lon(tile_x + 1, tile_y + 1, 14),
            get_tile_upper_left_lat_lon(tile_x, tile_y + 1, 14),
            get_tile_upper_left_lat_lon(tile_x, tile_y, 14),
        ]
        result.append(tile)
    return result


def make_grid_file_gpx(grid_points: list[list[list[float]]], stem: str) -> None:
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    for points in grid_points:
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        for point in points:
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*point))

    out_path = pathlib.Path("Explorer") / f"{stem}.gpx"
    out_path.parent.mkdir(exist_ok=True, parents=True)

    with open(out_path, "w") as f:
        f.write(gpx.to_xml())


def make_grid_file_geojson(grid_points: list[list[list[float]]], stem: str) -> None:
    fc = geojson.FeatureCollection(
        [
            geojson.Feature(
                geometry=geojson.Polygon([[[lon, lat] for lat, lon in points]])
            )
            for points in grid_points
        ]
    )

    out_path = pathlib.Path("Explorer") / f"{stem}.geojson"
    out_path.parent.mkdir(exist_ok=True, parents=True)

    with open(out_path, "w") as f:
        geojson.dump(fc, f, sort_keys=True, indent=4, ensure_ascii=False)
