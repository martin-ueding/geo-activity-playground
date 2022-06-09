import gpxpy
import pathlib

from ..core.tiles import get_tile_upper_left_lat_lon


def make_grid_file(west: int, north: int, east: int, south: int, path: pathlib.Path) -> None:
    points = []
    for tile_x in range(west, east):
        for tile_y in range(north, south):
            points.append(get_tile_upper_left_lat_lon(tile_x, tile_y, 14))

    gpx = gpxpy.gpx.GPX()

    for lat, lon in points:
        gpx.waypoints.append(gpxpy.gpx.GPXWaypoint(lat, lon))

    with open(path, 'w') as f:
        f.write(gpx.to_xml())