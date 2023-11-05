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
import pathlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn.cluster

from .core.sources import TimeSeriesSource
from .core.tiles import compute_tile
from .core.tiles import get_tile
from .core.tiles import latlon_to_xy

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
    # find tiles coordinates
    lat_min, lon_min = np.min(lat_lon_data, axis=0)
    lat_max, lon_max = np.max(lat_lon_data, axis=0)

    if arg_zoom > -1:
        zoom = min(arg_zoom, OSM_MAX_ZOOM)

        x_tile_min, y_tile_max = map(int, latlon_to_xy(lat_min, lon_min, zoom))
        x_tile_max, y_tile_min = map(int, latlon_to_xy(lat_max, lon_max, zoom))

    else:
        zoom = OSM_MAX_ZOOM

        while True:
            x_tile_min, y_tile_max = map(int, latlon_to_xy(lat_min, lon_min, zoom))
            x_tile_max, y_tile_min = map(int, latlon_to_xy(lat_max, lon_max, zoom))

            if (x_tile_max - x_tile_min + 1) * OSM_TILE_SIZE <= MAX_HEATMAP_SIZE[
                0
            ] and (y_tile_max - y_tile_min + 1) * OSM_TILE_SIZE <= MAX_HEATMAP_SIZE[1]:
                break

            zoom -= 1

        print("Auto zoom = {}".format(zoom))

    tile_count = (x_tile_max - x_tile_min + 1) * (y_tile_max - y_tile_min + 1)

    if tile_count > MAX_TILE_COUNT:
        exit("ERROR zoom value too high, too many tiles to download")

    supertile = np.zeros(
        (
            (y_tile_max - y_tile_min + 1) * OSM_TILE_SIZE,
            (x_tile_max - x_tile_min + 1) * OSM_TILE_SIZE,
            3,
        )
    )

    n = 0
    for x in range(x_tile_min, x_tile_max + 1):
        for y in range(y_tile_min, y_tile_max + 1):
            n += 1

            tile = np.array(get_tile(zoom, x, y)) / 255

            i = y - y_tile_min
            j = x - x_tile_min

            supertile[
                i * OSM_TILE_SIZE : (i + 1) * OSM_TILE_SIZE,
                j * OSM_TILE_SIZE : (j + 1) * OSM_TILE_SIZE,
                :,
            ] = tile[:, :, :3]

    supertile = np.sum(supertile * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
    supertile = 1.0 - supertile  # invert colors
    supertile = np.dstack((supertile, supertile, supertile))  # to rgb

    # fill trackpoints
    sigma_pixel = 1

    data = np.zeros(supertile.shape[:2])

    xy_data = latlon_to_xy(lat_lon_data[:, 0], lat_lon_data[:, 1], zoom)

    xy_data = np.array(xy_data).T
    xy_data = np.round(
        (xy_data - [x_tile_min, y_tile_min]) * OSM_TILE_SIZE
    )  # to supertile coordinates

    for j, i in xy_data.astype(int):
        data[
            i - sigma_pixel : i + sigma_pixel, j - sigma_pixel : j + sigma_pixel
        ] += 1.0

    res_pixel = (
        156543.03 * np.cos(np.radians(np.mean(lat_lon_data[:, 0]))) / (2.0**zoom)
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

    xy_data

    supertile = supertile[
        int(min(xy_data[:, 1])) : int(max(xy_data[:, 1])),
        int(min(xy_data[:, 0])) : int(max(xy_data[:, 0])),
        :,
    ]

    return supertile


def generate_heatmaps_per_cluster(ts_source: TimeSeriesSource) -> None:
    arrays = []
    names = []
    for i, df in enumerate(ts_source.iter_activities()):
        latlon = np.column_stack([df.latitude, df.longitude])
        names.extend([i] * len(df))
        arrays.append(latlon)
    latlon = np.row_stack(arrays)
    del arrays

    tiles = [compute_tile(lat, lon) for lat, lon in latlon]

    unique_tiles = set(tiles)
    unique_tiles_array = np.array(list(unique_tiles))

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

    print("Number of clusters", len(all_df.cluster.unique()))
    for i, (cluster_id, group) in enumerate(
        sorted(all_df.groupby("cluster"), key=lambda elem: len(elem[1]), reverse=True),
        start=1,
    ):
        if cluster_id == -1:
            continue
        print(f"Cluster {cluster_id} has {len(group)} elements.")
        latlon = np.column_stack([group.lat, group.lon])
        heatmap = render_heatmap(latlon, num_activities=len(group.activity.unique()))
        plt.imsave(output_dir / f"Cluster-{i}.png", heatmap)
