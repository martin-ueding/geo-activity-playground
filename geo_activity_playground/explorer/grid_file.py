import gpxpy
import pathlib

from ..core.tiles import get_tile_upper_left_lat_lon


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