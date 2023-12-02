# Copyright (c) 2018 Remi Salmon
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import logging
import pathlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn.cluster

from .core.sources import TimeSeriesSource
from .core.tiles import compute_tile
from .core.tiles import get_tile
from .core.tiles import latlon_to_xy
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.heatmap import add_margin_to_geo_bounds
from geo_activity_playground.core.heatmap import build_map_from_tiles
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import crop_image_to_bounds
from geo_activity_playground.core.heatmap import get_bounds
from geo_activity_playground.core.heatmap import get_sensible_zoom_level


logger = logging.getLogger(__name__)

# globals
PLT_COLORMAP = "hot"  # matplotlib color map
MAX_TILE_COUNT = 2000  # maximum number of tiles to download
MAX_HEATMAP_SIZE = (2160, 3840)  # maximum heatmap size in pixel

OSM_TILE_SIZE = 256  # OSM tile size in pixel
OSM_MAX_ZOOM = 19  # OSM maximum zoom level


def gaussian_filter(image, sigma):
    # returns image filtered with a gaussian function of variance sigma**2
    #
    # input: image = numpy.ndarray
    #        sigma = float
    # output: image = numpy.ndarray

    i, j = np.meshgrid(
        np.arange(image.shape[0]), np.arange(image.shape[1]), indexing="ij"
    )

    mu = (int(image.shape[0] / 2.0), int(image.shape[1] / 2.0))

    gaussian = (
        1.0
        / (2.0 * np.pi * sigma * sigma)
        * np.exp(-0.5 * (((i - mu[0]) / sigma) ** 2 + ((j - mu[1]) / sigma) ** 2))
    )

    gaussian = np.roll(gaussian, (-mu[0], -mu[1]), axis=(0, 1))

    image_fft = np.fft.rfft2(image)
    gaussian_fft = np.fft.rfft2(gaussian)

    image = np.fft.irfft2(image_fft * gaussian_fft)

    return image


def render_heatmap(
    lat_lon_data: np.ndarray, num_activities: int, arg_zoom: int = -1
) -> np.ndarray:
    geo_bounds = get_bounds(lat_lon_data)
    geo_bounds = add_margin_to_geo_bounds(geo_bounds)
    tile_bounds = get_sensible_zoom_level(geo_bounds)
    supertile = build_map_from_tiles(tile_bounds)
    supertile = convert_to_grayscale(supertile)
    supertile = 1.0 - supertile  # invert colors

    # fill trackpoints
    sigma_pixel = 1

    data = np.zeros(supertile.shape[:2])

    xy_data = latlon_to_xy(lat_lon_data[:, 0], lat_lon_data[:, 1], tile_bounds.zoom)

    xy_data = np.array(xy_data).T
    xy_data = np.round(
        (xy_data - [tile_bounds.x_tile_min, tile_bounds.y_tile_min]) * OSM_TILE_SIZE
    )  # to supertile coordinates

    for j, i in xy_data.astype(int):
        data[
            i - sigma_pixel : i + sigma_pixel, j - sigma_pixel : j + sigma_pixel
        ] += 1.0

    res_pixel = (
        156543.03
        * np.cos(np.radians(np.mean(lat_lon_data[:, 0])))
        / (2.0**tile_bounds.zoom)
    )  # from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames

    # trackpoint max accumulation per pixel = 1/5 (trackpoint/meter) * res_pixel (meter/pixel) * activities
    # (Strava records trackpoints every 5 meters in average for cycling activites)
    m = np.round((1.0 / 5.0) * res_pixel * num_activities)

    data[data > m] = m

    # equalize histogram and compute kernel density estimation
    data_hist, _ = np.histogram(data, bins=int(m + 1))

    data_hist = np.cumsum(data_hist) / data.size  # normalized cumulated histogram

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            data[i, j] = m * data_hist[int(data[i, j])]  # histogram equalization

    data = gaussian_filter(
        data, float(sigma_pixel)
    )  # kernel density estimation with normal kernel

    data = (data - data.min()) / (data.max() - data.min())  # normalize to [0,1]

    # colorize
    cmap = plt.get_cmap(PLT_COLORMAP)

    data_color = cmap(data)
    data_color[data_color == cmap(0.0)] = 0.0  # remove background color

    for c in range(3):
        supertile[:, :, c] = (1.0 - data_color[:, :, c]) * supertile[
            :, :, c
        ] + data_color[:, :, c]

    supertile = crop_image_to_bounds(supertile, geo_bounds, tile_bounds)
    return supertile


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
