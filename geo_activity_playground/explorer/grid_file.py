import pathlib
from typing import Iterator

import geojson
import gpxpy
import numpy as np
import pandas as pd
import scipy.ndimage

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.explorer.converters import get_tile_history


def get_three_color_tiles(
    tiles: pd.DataFrame, repository: ActivityRepository, zoom: int
) -> str:
    # Create array with visited tiles.
    a = np.zeros((2**zoom, 2**zoom), dtype=np.int8)
    a[tiles["tile_x"], tiles["tile_y"]] = 1

    tile_dict = {elem: 1 for elem in zip(tiles["tile_x"], tiles["tile_y"])}

    for x, y in tile_dict.keys():
        if (
            (x + 1, y) in tile_dict
            and (x - 1, y) in tile_dict
            and (x, y + 1) in tile_dict
            and (x, y - 1) in tile_dict
        ):
            tile_dict[(x, y)] = 2

    # Compute biggest square.
    square_size = 1
    biggest = None
    for x, y in sorted(tile_dict):
        while True:
            for i in range(square_size):
                for j in range(square_size):
                    if (x + i, y + j) not in tile_dict:
                        break
                else:
                    continue
                break
            else:
                biggest = (x, y, square_size)
                square_size += 1
                continue
            break

    if biggest is not None:
        square_x, square_y, square_size = biggest
        for x in range(square_x, square_x + square_size):
            for y in range(square_y, square_y + square_size):
                tile_dict[(x, y)] = 3

    tile_metadata = {
        (row["tile_x"], row["tile_y"]): {
            "first_visit": row["time"].date().isoformat(),
            "activity_id": row["activity_id"],
            "activity_name": repository.get_activity_by_id(row["activity_id"]).name,
        }
        for index, row in tiles.iterrows()
    }

    # Find non-zero tiles.
    return geojson.dumps(
        geojson.FeatureCollection(
            features=[
                make_explorer_tile(
                    x,
                    y,
                    {
                        "color": {1: "red", 2: "green", 3: "blue"}[v],
                        **tile_metadata[(x, y)],
                    },
                    zoom,
                )
                for (x, y), v in tile_dict.items()
            ]
        )
    )


def get_border_tiles(tiles: pd.DataFrame, zoom: int) -> list[list[list[float]]]:
    a = np.zeros((2**zoom, 2**zoom), dtype=np.int8)
    a[tiles["tile_x"], tiles["tile_y"]] = 1
    dilated = scipy.ndimage.binary_dilation(a, iterations=2)
    border = dilated - a
    border_x, border_y = np.where(border)
    return make_grid_points(zip(border_x, border_y), zoom)


def get_explored_tiles(tiles: pd.DataFrame, zoom: int) -> list[list[list[float]]]:
    return make_grid_points(zip(tiles["tile_x"], tiles["tile_y"]), zoom)


def make_explorer_tile(
    tile_x: int, tile_y: int, properties: dict, zoom: int
) -> geojson.Feature:
    corners = [
        get_tile_upper_left_lat_lon(*args)
        for args in [
            (tile_x, tile_y, zoom),
            (tile_x + 1, tile_y, zoom),
            (tile_x + 1, tile_y + 1, zoom),
            (tile_x, tile_y + 1, zoom),
            (tile_x, tile_y, zoom),
        ]
    ]
    return geojson.Feature(
        geometry=geojson.Polygon([[(coord[1], coord[0]) for coord in corners]]),
        properties=properties,
    )


def make_grid_points(
    tile_iterator: Iterator[tuple[int, int]], zoom: int
) -> list[list[list[float]]]:
    result = []
    for tile_x, tile_y in tile_iterator:
        tile = [
            get_tile_upper_left_lat_lon(tile_x, tile_y, zoom),
            get_tile_upper_left_lat_lon(tile_x + 1, tile_y, zoom),
            get_tile_upper_left_lat_lon(tile_x + 1, tile_y + 1, zoom),
            get_tile_upper_left_lat_lon(tile_x, tile_y + 1, zoom),
            get_tile_upper_left_lat_lon(tile_x, tile_y, zoom),
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

    out_path = pathlib.Path("Download") / f"{stem}.gpx"
    out_path.parent.mkdir(exist_ok=True, parents=True)

    with open(out_path, "w") as f:
        f.write(gpx.to_xml())


def make_grid_file_geojson(grid_points: list[list[list[float]]], stem: str) -> str:
    fc = geojson.FeatureCollection(
        [
            geojson.Feature(
                geometry=geojson.Polygon([[[lon, lat] for lat, lon in points]])
            )
            for points in grid_points
        ]
    )
    result = geojson.dumps(fc, sort_keys=True, indent=4, ensure_ascii=False)
    out_path = pathlib.Path("Download") / f"{stem}.geojson"
    out_path.parent.mkdir(exist_ok=True, parents=True)
    with open(out_path, "w") as f:
        f.write(result)
    return result


def get_explored_geojson(repository: ActivityRepository, zoom: int) -> str:
    tiles = get_tile_history(repository, zoom)
    return make_grid_file_geojson(
        make_grid_points(zip(tiles["tile_x"], tiles["tile_y"]))
    )
