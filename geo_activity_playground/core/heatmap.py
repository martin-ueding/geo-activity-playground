import dataclasses
import functools
import logging
import pathlib

import numpy as np
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import work_tracker
from geo_activity_playground.core.tiles import get_tile
from geo_activity_playground.core.tiles import latlon_to_xy


logger = logging.getLogger(__name__)


@functools.cache
def get_all_points(repository: ActivityRepository) -> pd.DataFrame:
    logger.info("Gathering all points …")
    all_points_path = pathlib.Path("Cache/all_points.parquet")
    if all_points_path.exists():
        all_points = pd.read_parquet(all_points_path)
    else:
        all_points = pd.DataFrame()
    new_shards = []
    with work_tracker(pathlib.Path("Cache/task_all_points.json")) as tracker:
        for activity in repository.iter_activities():
            if activity.id in tracker:
                continue
            tracker.add(activity.id)

            logger.info(f"Parsing points from {activity.id} …")
            time_series = repository.get_time_series(activity.id)
            if len(time_series) == 0 or "latitude" not in time_series.columns:
                continue
            new_shards.append(time_series[["latitude", "longitude"]])
    logger.info("Concatenating shards …")
    all_points = pd.concat([all_points] + new_shards)
    all_points.to_parquet(all_points_path)
    return all_points


@dataclasses.dataclass
class GeoBounds:
    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float


def get_bounds(lat_lon_data: np.array) -> GeoBounds:
    return GeoBounds(*np.min(lat_lon_data, axis=0), *np.max(lat_lon_data, axis=0))


MAX_HEATMAP_SIZE = (2160, 3840)  # maximum heatmap size in pixel
OSM_TILE_SIZE = 256  # OSM tile size in pixel
OSM_MAX_ZOOM = 19  # OSM maximum zoom level
MAX_TILE_COUNT = 2000  # maximum number of tiles to download


@dataclasses.dataclass
class TileBounds:
    zoom: int
    x_tile_min: int
    x_tile_max: int
    y_tile_min: int
    y_tile_max: int


def get_sensible_zoom_level(bounds: GeoBounds) -> TileBounds:
    zoom = OSM_MAX_ZOOM

    while True:
        x_tile_min, y_tile_max = map(
            int, latlon_to_xy(bounds.lat_min, bounds.lon_min, zoom)
        )
        x_tile_max, y_tile_min = map(
            int, latlon_to_xy(bounds.lat_max, bounds.lon_max, zoom)
        )

        if (x_tile_max - x_tile_min + 1) * OSM_TILE_SIZE <= MAX_HEATMAP_SIZE[0] and (
            y_tile_max - y_tile_min + 1
        ) * OSM_TILE_SIZE <= MAX_HEATMAP_SIZE[1]:
            break

        zoom -= 1

    tile_count = (x_tile_max - x_tile_min + 1) * (y_tile_max - y_tile_min + 1)

    if tile_count > MAX_TILE_COUNT:
        raise RuntimeError("Zoom value too high, too many tiles to download")

    return TileBounds(
        zoom=zoom,
        x_tile_min=x_tile_min,
        x_tile_max=x_tile_max,
        y_tile_min=y_tile_min,
        y_tile_max=y_tile_max,
    )


def build_map_from_tiles(tile_bounds: TileBounds) -> np.array:
    background = np.zeros(
        (
            (tile_bounds.y_tile_max - tile_bounds.y_tile_min + 1) * OSM_TILE_SIZE,
            (tile_bounds.x_tile_max - tile_bounds.x_tile_min + 1) * OSM_TILE_SIZE,
            3,
        )
    )

    for x in range(tile_bounds.x_tile_min, tile_bounds.x_tile_max + 1):
        for y in range(tile_bounds.y_tile_min, tile_bounds.y_tile_max + 1):
            tile = np.array(get_tile(tile_bounds.zoom, x, y)) / 255

            i = y - tile_bounds.y_tile_min
            j = x - tile_bounds.x_tile_min

            background[
                i * OSM_TILE_SIZE : (i + 1) * OSM_TILE_SIZE,
                j * OSM_TILE_SIZE : (j + 1) * OSM_TILE_SIZE,
                :,
            ] = tile[:, :, :3]

    return background


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
    image = np.dstack((image, image, image))
    return image
