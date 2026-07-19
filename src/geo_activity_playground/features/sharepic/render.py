import datetime
import io
import pathlib
import re

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from ...core.datamodel import Activity, MapConfig
from ...core.raster_map import (
    OSM_MAX_ZOOM,
    OSM_TILE_SIZE,
    map_image_from_tile_bounds,
    tile_bounds_around_center,
)

_SHAREPIC_FOOTER_HEIGHT = 115
_SHAREPIC_HEADER_HEIGHT = 50
_FONT_CANDIDATES = [
    "/usr/share/fonts/open-sans/OpenSans-Regular.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
    "/usr/share/fonts/adwaita-sans-fonts/AdwaitaSans-Regular.ttf",
]
_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/open-sans/OpenSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
]


def _get_font(
    size: int, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES
    for path in candidates:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def make_sharepic_base(time_series_list: list[pd.DataFrame], config: MapConfig):
    all_time_series = pd.concat(time_series_list)
    finite_mask = np.isfinite(all_time_series["x"]) & np.isfinite(all_time_series["y"])
    all_time_series = all_time_series.loc[finite_mask]

    target_width = 600
    target_height = 600
    footer_height = _SHAREPIC_FOOTER_HEIGHT
    header_height = _SHAREPIC_HEADER_HEIGHT
    target_map_height = target_height - footer_height - header_height

    if len(all_time_series) == 0:
        return Image.new("RGB", (target_width, target_height), "black")

    tile_x = all_time_series["x"]
    tile_y = all_time_series["y"]
    tile_width = tile_x.max() - tile_x.min()
    tile_height = tile_y.max() - tile_y.min()

    zoom_candidates = [OSM_MAX_ZOOM]
    if tile_width > 0:
        zoom_candidates.append(np.log2(target_width / tile_width / OSM_TILE_SIZE))
    if tile_height > 0:
        zoom_candidates.append(np.log2(target_map_height / tile_height / OSM_TILE_SIZE))
    zoom_float = min(zoom_candidates)
    zoom = int(np.clip(np.floor(zoom_float), 0, OSM_MAX_ZOOM))

    tile_xz = tile_x * 2**zoom
    tile_yz = tile_y * 2**zoom

    tile_xz_center = (
        (tile_xz.max() + tile_xz.min()) / 2,
        (tile_yz.max() + tile_yz.min()) / 2,
    )

    tile_bounds = tile_bounds_around_center(
        tile_xz_center, (target_width, target_map_height), zoom
    )
    tile_bounds.y1 -= header_height / OSM_TILE_SIZE
    tile_bounds.y2 += footer_height / OSM_TILE_SIZE
    background = map_image_from_tile_bounds(tile_bounds, config)

    img = Image.fromarray((background * 255).astype("uint8"), "RGB")
    draw = ImageDraw.Draw(img, mode="RGBA")

    map_center_y = header_height + target_map_height / 2

    for time_series in time_series_list:
        time_series = time_series.loc[
            np.isfinite(time_series["x"]) & np.isfinite(time_series["y"])
        ]
        if len(time_series) == 0:
            continue
        for _index, group in time_series.groupby("segment_id"):
            tile_xz = group["x"] * 2**zoom
            tile_yz = group["y"] * 2**zoom
            xy = list(
                zip(
                    (tile_xz - tile_xz_center[0]) * OSM_TILE_SIZE + target_width / 2,
                    (tile_yz - tile_xz_center[1]) * OSM_TILE_SIZE + map_center_y,
                )
            )
            draw.line(xy, fill=(255, 255, 255, 120), width=7)
            draw.line(xy, fill=(220, 50, 30), width=4)

    return img


def _draw_sharepic_stats(
    draw: ImageDraw.ImageDraw,
    img_width: int,
    footer_y: int,
    stat_items: list[tuple[str, str]],
) -> None:
    if not stat_items:
        return
    n = len(stat_items)
    col_w = img_width // n
    stat_y = footer_y + 42
    for i, (value, label) in enumerate(stat_items):
        x_center = i * col_w + col_w // 2
        draw.text(
            (x_center, stat_y),
            value,
            fill="white",
            font=_get_font(22, bold=True),
            anchor="mt",
        )
        draw.text(
            (x_center, stat_y + 28),
            label,
            fill=(140, 140, 140),
            font=_get_font(11),
            anchor="mt",
        )


def make_sharepic(
    activity: Activity,
    time_series: pd.DataFrame,
    sharepic_suppressed_fields: list[str],
    config: MapConfig,
) -> bytes:
    img = make_sharepic_base([time_series], config)
    draw = ImageDraw.Draw(img, mode="RGBA")

    # Header overlay: activity name
    draw.rectangle([0, 0, img.width, _SHAREPIC_HEADER_HEIGHT], fill=(10, 10, 10, 210))
    name = activity.name or ""
    draw.text(
        (16, (_SHAREPIC_HEADER_HEIGHT - 26) // 2),
        name,
        fill="white",
        font=_get_font(24, bold=True),
    )

    # Footer overlay
    footer_y = img.height - _SHAREPIC_FOOTER_HEIGHT
    draw.rectangle([0, footer_y, img.width, img.height], fill=(10, 10, 10, 215))

    # Secondary meta line: date · kind · equipment
    meta_parts = []
    if activity.start_local_tz and "start" not in sharepic_suppressed_fields:
        meta_parts.append(str(activity.start_local_tz.date()))
    if activity.kind and "kind" not in sharepic_suppressed_fields:
        meta_parts.append(activity.kind.name)
    if activity.equipment and "equipment" not in sharepic_suppressed_fields:
        meta_parts.append(activity.equipment.name)
    if meta_parts:
        draw.text(
            (16, footer_y + 12),
            "  ·  ".join(meta_parts),
            fill=(170, 170, 170),
            font=_get_font(14),
        )

    # Stats columns
    stat_items = []
    if "distance_km" not in sharepic_suppressed_fields:
        stat_items.append((f"{activity.distance_km:.1f} km", "DISTANCE"))
    if activity.elapsed_time and "elapsed_time" not in sharepic_suppressed_fields:
        stat_items.append((_format_elapsed_time(activity.elapsed_time), "DURATION"))
    if activity.calories and "calories" not in sharepic_suppressed_fields:
        stat_items.append((f"{activity.calories}", "KCAL"))
    if activity.steps and "steps" not in sharepic_suppressed_fields:
        stat_items.append((f"{activity.steps}", "STEPS"))
    _draw_sharepic_stats(draw, img.width, footer_y, stat_items)

    draw.text(
        (img.width - 8, img.height - 6),
        "Map: © OpenStreetMap Contributors",
        fill=(90, 90, 90),
        font=_get_font(11),
        anchor="rs",
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def make_day_sharepic(
    activities: pd.DataFrame,
    time_series_list: list[pd.DataFrame],
    config: MapConfig,
) -> bytes:
    img = make_sharepic_base(time_series_list, config)
    draw = ImageDraw.Draw(img, mode="RGBA")

    date = activities.iloc[0]["start_local"].date()
    distance_km = activities["distance_km"].sum()
    elapsed_time: pd.Timedelta = activities["elapsed_time"].sum()

    # Header: date
    draw.rectangle([0, 0, img.width, _SHAREPIC_HEADER_HEIGHT], fill=(10, 10, 10, 210))
    draw.text(
        (16, (_SHAREPIC_HEADER_HEIGHT - 26) // 2),
        str(date),
        fill="white",
        font=_get_font(24, bold=True),
    )

    # Footer overlay
    footer_y = img.height - _SHAREPIC_FOOTER_HEIGHT
    draw.rectangle([0, footer_y, img.width, img.height], fill=(10, 10, 10, 215))

    n_activities = len(activities)
    activity_label = (
        f"{n_activities} {'activity' if n_activities == 1 else 'activities'}"
    )
    draw.text(
        (16, footer_y + 12), activity_label, fill=(170, 170, 170), font=_get_font(14)
    )

    stat_items = [
        (f"{distance_km:.1f} km", "DISTANCE"),
        (_format_elapsed_time(elapsed_time), "DURATION"),
    ]
    _draw_sharepic_stats(draw, img.width, footer_y, stat_items)

    draw.text(
        (img.width - 8, img.height - 6),
        "Map: © OpenStreetMap Contributors",
        fill=(90, 90, 90),
        font=_get_font(11),
        anchor="rs",
    )

    f = io.BytesIO()
    img.save(f, format="png")
    return bytes(f.getbuffer())


def _format_elapsed_time(elapsed_time: datetime.timedelta | pd.Timedelta) -> str:
    rounded_seconds = round(pd.Timedelta(elapsed_time).total_seconds())
    rounded = datetime.timedelta(seconds=rounded_seconds)
    return re.sub(r"^0 days,? ", "", f"{rounded}")
