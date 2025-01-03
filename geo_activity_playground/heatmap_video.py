import collections
import datetime
import os
import pathlib

import matplotlib.pyplot as pl
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageDraw
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.heatmap import build_map_from_tiles_around_center
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import OSM_TILE_SIZE
from geo_activity_playground.core.tiles import compute_tile_float


def main_heatmap_video(options) -> None:
    zoom: int = options.zoom
    print(options)
    video_size = options.video_width, options.video_height
    os.chdir(options.basedir)

    repository = ActivityRepository()
    repository.reload()
    assert len(repository) > 0
    config_accessor = ConfigAccessor()

    center_xy = compute_tile_float(options.latitude, options.longitude, zoom)

    background = build_map_from_tiles_around_center(
        center_xy,
        zoom,
        video_size,
        video_size,
        config_accessor(),
    )
    background = convert_to_grayscale(background)
    background = 1.0 - background  # invert colors

    activities_per_day = collections.defaultdict(set)
    for activity in tqdm(
        repository.iter_activities(), desc="Gather activities per day"
    ):
        activities_per_day[activity["start"].date()].add(activity["id"])

    running_counts = np.zeros(background.shape[:2], np.float64)

    output_dir = pathlib.Path("Heatmap Video")
    output_dir.mkdir(exist_ok=True)

    first_day = min(activities_per_day)
    last_day = max(activities_per_day)
    days = pd.date_range(first_day, last_day)
    for current_day in tqdm(days, desc="Generate video frames"):
        for activity_id in activities_per_day[current_day.date()]:
            im = Image.new("L", video_size)
            draw = ImageDraw.Draw(im)

            time_series = repository.get_time_series(activity_id)
            for _, group in time_series.groupby("segment_id"):
                tile_xz = group["x"] * 2**zoom
                tile_yz = group["y"] * 2**zoom

                xy_pixels = list(
                    zip(
                        (tile_xz - center_xy[0]) * OSM_TILE_SIZE
                        + options.video_width / 2,
                        (tile_yz - center_xy[1]) * OSM_TILE_SIZE
                        + options.video_height / 2,
                    )
                )
                pixels = [int(value) for t in xy_pixels for value in t]
                draw.line(pixels, fill=1, width=max(3, 6 * (zoom - 17)))
                aim = np.array(im)
                running_counts += aim

        tile_counts = np.sqrt(running_counts) / 5
        tile_counts[tile_counts > 1.0] = 1.0

        cmap = pl.get_cmap(config_accessor().color_scheme_for_heatmap)
        data_color = cmap(tile_counts)
        data_color[data_color == cmap(0.0)] = 0.0  # remove background color

        rendered = np.zeros_like(background)
        for c in range(3):
            rendered[:, :, c] = (1.0 - data_color[:, :, c]) * background[
                :, :, c
            ] + data_color[:, :, c]

        img = Image.fromarray((rendered * 255).astype("uint8"), "RGB")
        img.save(output_dir / f"{current_day.date()}.png", format="png")

        running_counts *= 1 - options.decay