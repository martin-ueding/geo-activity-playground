import gpxpy
import pathlib
import numpy as np
import pandas as pd
import scipy.ndimage

from .converters import cache_dir
from ..core.tiles import get_tile_upper_left_lat_lon


def get_border_tiles():
    tiles = pd.read_json(cache_dir / 'tiles.json')
    tiles.Time = pd.to_datetime(tiles.Time)
    a = np.zeros((2**14, 2**14), dtype=np.int8)
    a[tiles["Tile X"], tiles["Tile Y"]] = 1
    dilated = scipy.ndimage.binary_dilation(a, iterations=5)
    border = dilated - a
    border_x, border_y = np.where(border)
    return border_x, border_y


def make_adapted_grid_file(border_x, border_y, path: pathlib.Path):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    for tile_x, tile_y in zip(border_x, border_y):
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y, 14)))
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(
            *get_tile_upper_left_lat_lon(tile_x + 1, tile_y, 14)))
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(
            *get_tile_upper_left_lat_lon(tile_x + 1, tile_y + 1, 14)))
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(
            *get_tile_upper_left_lat_lon(tile_x, tile_y + 1, 14)))
        gpx_segment.points.append(
            gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y, 14)))

    with open(pathlib.Path('~/Dokumente/Karten/Routen/Explorer 3.gpx').expanduser(),
              'w') as f:
        f.write(gpx.to_xml())


def make_grid_file(west: int, north: int, east: int, south: int, path: pathlib.Path) -> None:
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    for tile_x in range(west, east):
        for tile_y in range(north, south):
            gpx_segment = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y, 14)))
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x+1, tile_y, 14)))
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x+1, tile_y+1, 14)))
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y+1, 14)))
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*get_tile_upper_left_lat_lon(tile_x, tile_y, 14)))

    with open(path, 'w') as f:
        f.write(gpx.to_xml())