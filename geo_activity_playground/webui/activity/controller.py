import datetime
import io
import logging
import re
from typing import Optional

import altair as alt
import geojson
import matplotlib
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageDraw

from ...explorer.grid_file import make_grid_file_geojson
from ...explorer.grid_file import make_grid_points
from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import make_geojson_color_line
from geo_activity_playground.core.activities import make_geojson_from_time_series
from geo_activity_playground.core.activities import make_speed_color_bar
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.heart_rate import HeartRateZoneComputer
from geo_activity_playground.core.heatmap import add_margin_to_geo_bounds
from geo_activity_playground.core.heatmap import build_map_from_tiles
from geo_activity_playground.core.heatmap import build_map_from_tiles_around_center
from geo_activity_playground.core.heatmap import GeoBounds
from geo_activity_playground.core.heatmap import get_bounds
from geo_activity_playground.core.heatmap import get_sensible_zoom_level
from geo_activity_playground.core.heatmap import OSM_MAX_ZOOM
from geo_activity_playground.core.heatmap import OSM_TILE_SIZE
from geo_activity_playground.core.heatmap import PixelBounds
from geo_activity_playground.core.heatmap import TileBounds
from geo_activity_playground.core.privacy_zones import PrivacyZone
from geo_activity_playground.core.tiles import compute_tile_float
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor

logger = logging.getLogger(__name__)


class ActivityController:
    def __init__(
        self,
        repository: ActivityRepository,
        tile_visit_accessor: TileVisitAccessor,
        config: Config,
    ) -> None:
        self._repository = repository
        self._tile_visit_accessor = tile_visit_accessor
        self._config = config
        self._heart_rate_zone_computer = HeartRateZoneComputer(config)

    def render_activity(self, id: int) -> dict:
        activity = self._repository.get_activity_by_id(id)

        time_series = self._repository.get_time_series(id)
        line_json = make_geojson_from_time_series(time_series)

        meta = self._repository.meta
        similar_activities = meta.loc[
            (meta.name == activity["name"]) & (meta.id != activity["id"])
        ]
        similar_activities = [row for _, row in similar_activities.iterrows()]
        similar_activities.reverse()

        new_tiles = {
            zoom: sum(
                self._tile_visit_accessor.tile_state["tile_history"][zoom][
                    "activity_id"
                ]
                == activity["id"]
            )
            for zoom in sorted(self._config.explorer_zoom_levels)
        }

        new_tiles_geojson = {}
        new_tiles_per_zoom = {}
        for zoom in sorted(self._config.explorer_zoom_levels):
            new_tiles = self._tile_visit_accessor.tile_state["tile_history"][zoom].loc[
                self._tile_visit_accessor.tile_state["tile_history"][zoom][
                    "activity_id"
                ]
                == activity["id"]
            ]
            if len(new_tiles):
                points = make_grid_points(
                    (
                        (row["tile_x"], row["tile_y"])
                        for index, row in new_tiles.iterrows()
                    ),
                    zoom,
                )
                new_tiles_geojson[zoom] = make_grid_file_geojson(points)
            new_tiles_per_zoom[zoom] = len(new_tiles)

        result = {
            "activity": activity,
            "line_json": line_json,
            "distance_time_plot": distance_time_plot(time_series),
            "color_line_geojson": make_geojson_color_line(time_series),
            "speed_time_plot": speed_time_plot(time_series),
            "speed_distribution_plot": speed_distribution_plot(time_series),
            "similar_activites": similar_activities,
            "speed_color_bar": make_speed_color_bar(time_series),
            "date": activity["start"].date(),
            "time": activity["start"].time(),
            "new_tiles": new_tiles_per_zoom,
            "new_tiles_geojson": new_tiles_geojson,
        }
        if (
            heart_zones := _extract_heart_rate_zones(
                time_series, self._heart_rate_zone_computer
            )
        ) is not None:
            result["heart_zones_plot"] = heart_rate_zone_plot(heart_zones)
        if "altitude" in time_series.columns:
            result["altitude_time_plot"] = altitude_time_plot(time_series)
        if "heartrate" in time_series.columns:
            result["heartrate_time_plot"] = heart_rate_time_plot(time_series)
        if "cadence" in time_series.columns:
            result["cadence_time_plot"] = cadence_time_plot(time_series)
        return result

    def render_sharepic(self, id: int) -> bytes:
        activity = self._repository.get_activity_by_id(id)
        time_series = self._repository.get_time_series(id)
        for coordinates in self._config.privacy_zones.values():
            privacy_zone = PrivacyZone(coordinates)
            time_series = privacy_zone.filter_time_series(time_series)
        if len(time_series) == 0:
            time_series = self._repository.get_time_series(id)
        return make_sharepic(
            activity, time_series, self._config.sharepic_suppressed_fields
        )

    def render_day(self, year: int, month: int, day: int) -> dict:
        meta = self._repository.meta
        selection = meta["start"].dt.date == datetime.date(year, month, day)
        activities_that_day = meta.loc[selection]

        time_series = [
            self._repository.get_time_series(activity_id)
            for activity_id in activities_that_day["id"]
        ]

        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in ts.groupby("segment_id")
                        ]
                    ),
                    properties={"color": matplotlib.colors.to_hex(cmap(i % 8))},
                )
                for i, ts in enumerate(time_series)
            ]
        )

        activities_list = activities_that_day.to_dict(orient="records")
        for i, activity_record in enumerate(activities_list):
            activity_record["color"] = matplotlib.colors.to_hex(cmap(i % 8))

        return {
            "activities": activities_list,
            "geojson": geojson.dumps(fc),
            "date": datetime.date(year, month, day).isoformat(),
            "total_distance": activities_that_day["distance_km"].sum(),
            "total_elapsed_time": activities_that_day["elapsed_time"].sum(),
        }

    def render_all(self) -> dict:
        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in self._repository.get_time_series(
                                activity["id"]
                            ).groupby("segment_id")
                        ]
                    ),
                    properties={
                        "color": matplotlib.colors.to_hex(cmap(i % 8)),
                        "activity_name": activity["name"],
                        "activity_id": str(activity["id"]),
                    },
                )
                for i, activity in enumerate(self._repository.iter_activities())
            ]
        )

        return {
            "geojson": geojson.dumps(fc),
        }

    def render_name(self, name: str) -> dict:
        meta = self._repository.meta
        selection = meta["name"] == name
        activities_with_name = meta.loc[selection]

        time_series = [
            self._repository.get_time_series(activity_id)
            for activity_id in activities_with_name["id"]
        ]

        cmap = matplotlib.colormaps["Dark2"]
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.MultiLineString(
                        coordinates=[
                            [
                                [lon, lat]
                                for lat, lon in zip(
                                    group["latitude"], group["longitude"]
                                )
                            ]
                            for _, group in ts.groupby("segment_id")
                        ]
                    ),
                    properties={"color": matplotlib.colors.to_hex(cmap(i % 8))},
                )
                for i, ts in enumerate(time_series)
            ]
        )

        activities_list = activities_with_name.to_dict(orient="records")
        for i, activity_record in enumerate(activities_list):
            activity_record["color"] = matplotlib.colors.to_hex(cmap(i % 8))

        return {
            "activities": activities_list,
            "geojson": geojson.dumps(fc),
            "name": name,
            "tick_plot": name_tick_plot(activities_with_name),
            "equipment_plot": name_equipment_plot(activities_with_name),
            "distance_plot": name_distance_plot(activities_with_name),
            "minutes_plot": name_minutes_plot(activities_with_name),
        }


def speed_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Speed")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("speed", title="Speed / km/h"),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def speed_distribution_plot(time_series: pd.DataFrame) -> str:
    df = pd.DataFrame(
        {
            "speed": time_series["speed"],
            "step": time_series["time"].diff().dt.total_seconds() / 60,
        }
    ).dropna()
    return (
        alt.Chart(df.loc[df["speed"] > 0], title="Speed distribution")
        .mark_bar()
        .encode(
            alt.X("speed", bin=alt.Bin(step=5), title="Speed / km/h"),
            alt.Y("sum(step)", title="Duration / min"),
        )
        .to_json(format="vega")
    )


def distance_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Distance")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("distance_km", title="Distance / km"),
            alt.Color("segment_id:N", title="Segment"),
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
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def heart_rate_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Heart Rate")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("heartrate", scale=alt.Scale(zero=False), title="Heart rate"),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def cadence_time_plot(time_series: pd.DataFrame) -> str:
    return (
        alt.Chart(time_series, title="Cadence")
        .mark_line()
        .encode(
            alt.X("time", title="Time"),
            alt.Y("cadence", title="Cadence"),
            alt.Color("segment_id:N", title="Segment"),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )


def heart_rate_zone_plot(heart_zones: pd.DataFrame) -> str:
    return (
        alt.Chart(heart_zones, title="Heart Rate Zones")
        .mark_bar()
        .encode(
            alt.X("minutes", title="Duration / min"),
            alt.Y("heartzone:O", title="Zone"),
            alt.Color("heartzone:O", scale=alt.Scale(scheme="turbo"), title="Zone"),
        )
        .to_json(format="vega")
    )


def name_tick_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Repetitions")
        .mark_tick()
        .encode(
            alt.X("start", title="Date"),
        )
        .to_json(format="vega")
    )


def name_equipment_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Equipment")
        .mark_bar()
        .encode(alt.X("count()", title="Count"), alt.Y("equipment", title="Equipment"))
        .to_json(format="vega")
    )


def name_distance_plot(meta: pd.DataFrame) -> str:
    return (
        alt.Chart(meta, title="Distance")
        .mark_bar()
        .encode(
            alt.X("distance_km", bin=True, title="Distance / km"),
            alt.Y("count()", title="Count"),
        )
        .to_json(format="vega")
    )


def name_minutes_plot(meta: pd.DataFrame) -> str:
    minutes = meta["elapsed_time"].dt.total_seconds() / 60
    return (
        alt.Chart(pd.DataFrame({"minutes": minutes}), title="Elapsed time")
        .mark_bar()
        .encode(
            alt.X("minutes", bin=True, title="Time / min"),
            alt.Y("count()", title="Count"),
        )
        .to_json(format="vega")
    )


def make_pixel_bounds_square(bounds: PixelBounds) -> PixelBounds:
    x_radius = (bounds.x_max - bounds.x_min) // 2
    y_radius = (bounds.y_max - bounds.y_min) // 2
    x_center = (bounds.x_max + bounds.x_min) // 2
    y_center = (bounds.y_max + bounds.y_min) // 2

    radius = max(x_radius, y_radius)

    return PixelBounds(
        x_min=x_center - radius,
        y_min=y_center - radius,
        x_max=x_center + radius,
        y_max=y_center + radius,
    )


def make_tile_bounds_square(bounds: TileBounds) -> TileBounds:
    x_radius = (bounds.x_tile_max - bounds.x_tile_min) / 2
    y_radius = (bounds.y_tile_max - bounds.y_tile_min) / 2
    x_center = (bounds.x_tile_max + bounds.x_tile_min) / 2
    y_center = (bounds.y_tile_max + bounds.y_tile_min) / 2

    radius = max(x_radius, y_radius)

    return TileBounds(
        zoom=bounds.zoom,
        x_tile_min=int(x_center - radius),
        y_tile_min=int(y_center - radius),
        x_tile_max=int(np.ceil(x_center + radius)),
        y_tile_max=int(np.ceil(y_center + radius)),
    )


def get_crop_mask(geo_bounds: GeoBounds, tile_bounds: TileBounds) -> PixelBounds:
    min_x, min_y = compute_tile_float(
        geo_bounds.lat_max, geo_bounds.lon_min, tile_bounds.zoom
    )
    max_x, max_y = compute_tile_float(
        geo_bounds.lat_min, geo_bounds.lon_max, tile_bounds.zoom
    )

    crop_mask = PixelBounds(
        int((min_x - tile_bounds.x_tile_min) * OSM_TILE_SIZE),
        int((max_x - tile_bounds.x_tile_min) * OSM_TILE_SIZE),
        int((min_y - tile_bounds.y_tile_min) * OSM_TILE_SIZE),
        int((max_y - tile_bounds.y_tile_min) * OSM_TILE_SIZE),
    )
    crop_mask = make_pixel_bounds_square(crop_mask)

    return crop_mask


def pixels_in_bounds(bounds: PixelBounds) -> int:
    return (bounds.x_max - bounds.x_min) * (bounds.y_max - bounds.y_min)


def make_sharepic(
    activity: ActivityMeta,
    time_series: pd.DataFrame,
    sharepic_suppressed_fields: list[str],
) -> bytes:
    tile_x = time_series["x"]
    tile_y = time_series["y"]
    tile_width = tile_x.max() - tile_x.min()
    tile_height = tile_y.max() - tile_y.min()

    target_width = 600
    target_height = 600
    footer_height = 100
    target_map_height = target_height - footer_height

    zoom = int(
        min(
            np.log2(target_width / tile_width / OSM_TILE_SIZE),
            np.log2(target_map_height / tile_height / OSM_TILE_SIZE),
            OSM_MAX_ZOOM,
        )
    )

    tile_xz = tile_x * 2**zoom
    tile_yz = tile_y * 2**zoom

    tile_xz_center = (
        (tile_xz.max() + tile_xz.min()) / 2,
        (tile_yz.max() + tile_yz.min()) / 2,
    )

    background = build_map_from_tiles_around_center(
        tile_xz_center,
        zoom,
        (target_width, target_height),
        (target_width, target_map_height),
    )

    img = Image.fromarray((background * 255).astype("uint8"), "RGB")
    draw = ImageDraw.Draw(img, mode="RGBA")

    for _, group in time_series.groupby("segment_id"):
        yx = list(
            zip(
                (tile_xz - tile_xz_center[0]) * OSM_TILE_SIZE + target_width / 2,
                (tile_yz - tile_xz_center[1]) * OSM_TILE_SIZE + target_map_height / 2,
            )
        )

        draw.line(yx, fill="red", width=4)

    draw.rectangle(
        [0, img.height - footer_height, img.width, img.height], fill=(0, 0, 0, 180)
    )

    facts = {
        "kind": f"{activity['kind']}",
        "start": f"{activity['start'].date()}",
        "equipment": f"{activity['equipment']}",
        "distance_km": f"\n{activity['distance_km']:.1f} km",
        "elapsed_time": re.sub(r"^0 days ", "", f"{activity['elapsed_time']}"),
    }

    if activity.get("calories", 0) and not pd.isna(activity["calories"]):
        facts["calories"] = f"{activity['calories']:.0f} kcal"
    if activity.get("steps", 0) and not pd.isna(activity["steps"]):
        facts["steps"] = f"{activity['steps']:.0f} steps"

    facts = {
        key: value
        for key, value in facts.items()
        if not key in sharepic_suppressed_fields
    }

    draw.text(
        (35, img.height - footer_height + 10),
        "      ".join(facts.values()),
        font_size=20,
    )

    draw.text(
        (img.width - 250, img.height - 20),
        "Map: © Open Street Map Contributors",
        font_size=14,
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def _extract_heart_rate_zones(
    time_series: pd.DataFrame, heart_rate_zone_computer: HeartRateZoneComputer
) -> Optional[pd.DataFrame]:
    if "heartrate" not in time_series:
        return

    try:
        zones = heart_rate_zone_computer.compute_zones(
            time_series["heartrate"], time_series["time"].iloc[0].year
        )
    except RuntimeError:
        return

    df = pd.DataFrame({"heartzone": zones, "step": time_series["time"].diff()}).dropna()
    duration_per_zone = df.groupby("heartzone").sum()["step"].dt.total_seconds() / 60
    duration_per_zone.name = "minutes"
    for i in range(6):
        if i not in duration_per_zone:
            duration_per_zone.loc[i] = 0.0
    result = duration_per_zone.reset_index()
    return result
