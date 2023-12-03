import datetime
import logging
import pathlib
from typing import Iterator

import geojson
import gpxpy
import matplotlib
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.explorer.clusters import ExplorerClusterState
from geo_activity_playground.explorer.converters import get_tile_history


logger = logging.getLogger(__name__)


def get_three_color_tiles(
    tiles: pd.DataFrame,
    repository: ActivityRepository,
    cluster_state: ExplorerClusterState,
    zoom: int,
) -> str:
    logger.info("Generate data for explorer tile map …")
    today = datetime.date.today()
    cmap_first = matplotlib.colormaps["plasma"]
    cmap_last = matplotlib.colormaps["plasma"]
    tile_dict = {}
    for index, row in tiles.iterrows():
        first_age_days = (today - row["first_time"].date()).days
        last_age_days = (today - row["last_time"].date()).days
        tile_dict[(row["tile_x"], row["tile_y"])] = {
            "first_activity_id": str(row["first_id"]),
            "first_activity_name": repository.get_activity_by_id(row["first_id"]).name,
            "last_activity_id": str(row["last_id"]),
            "last_activity_name": repository.get_activity_by_id(row["last_id"]).name,
            "first_age_days": first_age_days,
            "first_age_color": matplotlib.colors.to_hex(
                cmap_first(max(1 - first_age_days / (2 * 365), 0.0))
            ),
            "last_age_days": last_age_days,
            "last_age_color": matplotlib.colors.to_hex(
                cmap_last(max(1 - last_age_days / (2 * 365), 0.0))
            ),
            "cluster": False,
            "color": None,
            "first_visit": row["first_time"].date().isoformat(),
            "last_visit": row["last_time"].date().isoformat(),
            "num_visits": row["count"],
            "square": False,
        }

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
                tile_dict[(x, y)]["square"] = True
                tile_dict[(x, y)]["color"] = "blue"

    # Add cluster information.
    for xy, members in cluster_state.cluster_tiles.items():
        tile_dict[xy]["this_cluster_size"] = len(members)
        tile_dict[xy]["cluster"] = True
    if len(cluster_state.cluster_evolution) > 0:
        max_cluster_size = cluster_state.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_size = 0
    num_cluster_tiles = len(cluster_state.cluster_tiles)

    # Apply cluster colors.
    for xy, xy_dict in tile_dict.items():
        if xy_dict["square"]:
            xy_dict["color"] = "blue"
        elif xy_dict["cluster"]:
            xy_dict["color"] = "green"
        else:
            xy_dict["color"] = "red"

    result = {
        "explored_geojson": geojson.dumps(
            geojson.FeatureCollection(
                features=[
                    make_explorer_tile(
                        x,
                        y,
                        tile_dict[(x, y)],
                        zoom,
                    )
                    for (x, y), v in tile_dict.items()
                ]
            )
        ),
        "max_cluster_size": max_cluster_size,
        "num_cluster_tiles": num_cluster_tiles,
        "num_tiles": len(tile_dict),
        "square_size": square_size,
    }
    return result


def get_border_tiles(tiles: pd.DataFrame, zoom: int) -> list[list[list[float]]]:
    logger.info("Generate border tiles …")
    tile_set = set(zip(tiles["tile_x"], tiles["tile_y"]))
    border_tiles = set()
    for x, y in tile_set:
        for neighbor in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
            if neighbor not in tile_set:
                border_tiles.add(neighbor)
    return make_grid_points(border_tiles, zoom)


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
