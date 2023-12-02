import functools
import io

import altair as alt
import matplotlib.pyplot as pl
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageDraw

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import extract_heart_rate_zones
from geo_activity_playground.core.activities import make_geojson_color_line
from geo_activity_playground.core.activities import make_geojson_from_time_series
from geo_activity_playground.core.heatmap import add_margin_to_geo_bounds
from geo_activity_playground.core.heatmap import build_map_from_tiles
from geo_activity_playground.core.heatmap import convert_to_grayscale
from geo_activity_playground.core.heatmap import crop_image_to_bounds
from geo_activity_playground.core.heatmap import gaussian_filter
from geo_activity_playground.core.heatmap import get_bounds
from geo_activity_playground.core.heatmap import get_sensible_zoom_level
from geo_activity_playground.core.heatmap import OSM_TILE_SIZE
from geo_activity_playground.core.tiles import latlon_to_xy


class ActivityController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.lru_cache()
    def render_activity(self, id: int) -> dict:
        activity = self._repository.get_activity_by_id(id)

        time_series = self._repository.get_time_series(id)
        line_json = make_geojson_from_time_series(time_series)

        result = {
            "activity": activity,
            "line_json": line_json,
            "distance_time_plot": distance_time_plot(time_series),
            "color_line_geojson": make_geojson_color_line(time_series),
        }
        if (heart_zones := extract_heart_rate_zones(time_series)) is not None:
            result["heart_zones_plot"] = heartrate_zone_plot(heart_zones)
        if "altitude" in time_series.columns:
            result["altitude_time_plot"] = altitude_time_plot(time_series)
        if "heartrate" in time_series.columns:
            result["heartrate_time_plot"] = heartrate_time_plot(time_series)
        return result

    def render_sharepic(self, id: int) -> bytes:
        time_series = self._repository.get_time_series(id)
        return make_sharepic(time_series)


def distance_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Distance")
        .mark_line()
        .encode(
            alt.X("time", title="Time"), alt.Y("distance/km", title="Distance / km")
        )
        .interactive()
        .to_json(format="vega")
    )


def altitude_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Altitude")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("altitude", scale=alt.Scale(zero=False), title="Altitude / m"),
        )
        .interactive()
        .to_json(format="vega")
    )


def heartrate_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Heart Rate")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("heartrate", scale=alt.Scale(zero=False), title="Heart rate"),
        )
        .interactive()
        .to_json(format="vega")
    )


def heartrate_zone_plot(heart_zones: pd.DataFrame) -> str:
    return (
        alt.Chart(heart_zones, title="Heart Rate Zones")
        .mark_bar()
        .encode(
            alt.X("minutes", title="Minutes"),
            alt.Y("heartzone:O", title="Zone"),
            alt.Color("heartzone:O", scale=alt.Scale(scheme="turbo"), title="Zone"),
        )
        .interactive()
        .to_json(format="vega")
    )


def make_sharepic(time_series: pd.DataFrame) -> bytes:
    lat_lon_data = np.array([time_series["latitude"], time_series["longitude"]]).T

    geo_bounds = get_bounds(lat_lon_data)
    geo_bounds = add_margin_to_geo_bounds(geo_bounds)
    tile_bounds = get_sensible_zoom_level(geo_bounds, (1500, 1500))
    background = build_map_from_tiles(tile_bounds)
    # background = convert_to_grayscale(background)

    xs, ys = latlon_to_xy(
        time_series["latitude"], time_series["longitude"], tile_bounds.zoom
    )
    yx = list(
        (
            int((x - tile_bounds.x_tile_min) * OSM_TILE_SIZE),
            int((y - tile_bounds.y_tile_min) * OSM_TILE_SIZE),
        )
        for x, y in zip(xs, ys)
    )

    img = Image.new("RGB", tile_bounds.shape[::-1])
    draw = ImageDraw.Draw(img)
    draw.line(yx, fill="red", width=3)

    aimg = np.array(img) / 255
    aimg[:, :, 0] = gaussian_filter(aimg[:, :, 0], 1)

    weight = np.dstack([aimg[:, :, 0]] * 3)

    background = (1 - weight) * background + aimg
    background[background > 1.0] = 1.0
    background[background < 0.0] = 0.0

    background = crop_image_to_bounds(background, geo_bounds, tile_bounds)

    f = io.BytesIO()
    pl.imsave(f, background, format="png")
    return bytes(f.getbuffer())
