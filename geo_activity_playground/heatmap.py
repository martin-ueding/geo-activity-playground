import logging
import pathlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn.cluster

from .core.tiles import compute_tile
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import add_margin_to_geo_bounds
from geo_activity_playground.core.heatmap import build_heatmap_image
from geo_activity_playground.core.heatmap import build_map_from_tiles
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import crop_image_to_bounds
from geo_activity_playground.core.heatmap import get_bounds
from geo_activity_playground.core.heatmap import get_sensible_zoom_level


logger = logging.getLogger(__name__)


def render_heatmap(
    lat_lon_data: np.ndarray, num_activities: int, arg_zoom: int = -1
) -> np.ndarray:
    geo_bounds = get_bounds(lat_lon_data)
    geo_bounds = add_margin_to_geo_bounds(geo_bounds)
    tile_bounds = get_sensible_zoom_level(geo_bounds, (2160, 3840))
    background = build_map_from_tiles(tile_bounds)
    background = convert_to_grayscale(background)
    background = 1.0 - background
    data_color = build_heatmap_image(lat_lon_data, num_activities, tile_bounds)
    for c in range(3):
        background[:, :, c] = (1.0 - data_color[:, :, c]) * background[
            :, :, c
        ] + data_color[:, :, c]
    background = crop_image_to_bounds(background, geo_bounds, tile_bounds)
    return background


def generate_heatmaps_per_cluster(repository: ActivityRepository) -> None:
    logger.info("Gathering data points …")
    arrays = []
    names = []
    for activity in repository.iter_activities():
        df = repository.get_time_series(activity.id)
        if "latitude" in df.columns:
            latlon = np.column_stack([df["latitude"], df["longitude"]])
            names.extend([activity.id] * len(df))
            arrays.append(latlon)
    latlon = np.row_stack(arrays)
    del arrays

    logger.info("Compute tiles for each point …")
    tiles = [compute_tile(lat, lon, 14) for lat, lon in latlon]

    unique_tiles = set(tiles)
    unique_tiles_array = np.array(list(unique_tiles))

    logger.info("Run DBSCAN cluster finding algorithm …")
    dbscan = sklearn.cluster.DBSCAN(eps=5, min_samples=3)
    labels = dbscan.fit_predict(unique_tiles_array)

    cluster_mapping = {
        tuple(xy): label for xy, label in zip(unique_tiles_array, labels)
    }

    all_df = pd.DataFrame(latlon, columns=["lat", "lon"])
    all_df["cluster"] = [cluster_mapping[xy] for xy in tiles]
    all_df["activity"] = names

    del labels
    del names

    output_dir = pathlib.Path("Heatmaps")
    output_dir.mkdir(exist_ok=True)
    for old_image in output_dir.glob("*.png"):
        old_image.unlink()

    logger.info(f"Found {len(all_df.cluster.unique())} clusters …")
    for i, (cluster_id, group) in enumerate(
        sorted(all_df.groupby("cluster"), key=lambda elem: len(elem[1]), reverse=True),
        start=1,
    ):
        if cluster_id == -1:
            continue
        logger.info(
            f"Rendering heatmap for cluster {cluster_id} with {len(group)} elements …"
        )
        latlon = np.column_stack([group.lat, group.lon])
        heatmap = render_heatmap(latlon, num_activities=len(group.activity.unique()))
        plt.imsave(output_dir / f"Cluster-{i}.png", heatmap)
