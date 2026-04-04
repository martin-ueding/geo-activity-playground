import datetime
import logging
from collections.abc import Callable, Sequence
from typing import Any

import geojson
import matplotlib
import numpy as np
import pandas as pd
import sqlalchemy

from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Kind,
    query_activity_meta,
)

logger = logging.getLogger(__name__)


MARKER_PROGRESS_STOPS: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


class ActivityRepository:
    def __len__(self) -> int:
        return DB.session.scalars(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(Activity)
        ).one()

    def has_activity(self, activity_id: int) -> bool:
        return bool(
            DB.session.scalars(
                sqlalchemy.query(Activity).where(Activity.id == activity_id)
            ).all()
        )

    def last_activity_date(self) -> datetime.datetime | None:
        result = DB.session.scalars(
            sqlalchemy.select(Activity).order_by(Activity.start)
        ).all()
        if result:
            return result[-1].start_local_tz
        else:
            return None

    def get_activity_ids(self, only_achievements: bool = False) -> Sequence[int]:
        query = sqlalchemy.select(Activity.id)
        if only_achievements:
            query = query.where(Kind.consider_for_achievements)
        result = DB.session.scalars(query.order_by(Activity.start, Activity.id)).all()
        return result

    def iter_activities(self, new_to_old=True, drop_na=False) -> Sequence[Activity]:
        query = sqlalchemy.select(Activity)
        if drop_na:
            query = query.where(Activity.start.is_not(None))
        result = DB.session.scalars(query.order_by(Activity.start)).all()
        direction = -1 if new_to_old else 1
        return result[::direction]

    def get_activity_by_id(self, id: int) -> Activity:
        activity = DB.session.scalar(
            sqlalchemy.select(Activity).where(Activity.id == int(id))
        )
        if activity is None:
            raise ValueError(f"Cannot find activity {id} in DB.session.")
        return activity

    def get_time_series(self, id: int) -> pd.DataFrame:
        return self.get_activity_by_id(id).time_series

    @property
    def meta(self) -> pd.DataFrame:
        df = query_activity_meta()

        return df


def make_geojson_progress_markers_from_time_series(time_series: pd.DataFrame) -> str:
    feature_collection = geojson.FeatureCollection(
        _make_progress_marker_features(time_series)
    )
    return geojson.dumps(feature_collection)


def make_geojson_from_time_series(time_series: pd.DataFrame) -> str:
    features = []
    for _, group in time_series.groupby("segment_id"):
        features.append(
            geojson.LineString(
                [(lon, lat) for lat, lon in zip(group["latitude"], group["longitude"])]
            )
        )

    features.extend(_make_progress_marker_features(time_series))

    fc = geojson.FeatureCollection(features=features)
    return geojson.dumps(fc)


def inter_quartile_range(values):
    return np.quantile(values, 0.75) - np.quantile(values, 0.25)


def make_geojson_color_line(time_series: pd.DataFrame, column: str) -> str:
    low, high, clamp_value = _make_value_clamp(time_series[column])
    cmap = matplotlib.colormaps["viridis"]
    features = [
        geojson.Feature(
            geometry=geojson.LineString(
                coordinates=[
                    [row["longitude"], row["latitude"]],
                    [next_row["longitude"], next_row["latitude"]],
                ]
            ),
            properties={
                column: (next_row[column] if np.isfinite(next_row[column]) else 0.0),
                "color": matplotlib.colors.to_hex(cmap(clamp_value(next_row[column]))),
            },
        )
        for _, group in time_series.groupby("segment_id")
        for (_, row), (_, next_row) in zip(group.iterrows(), group.iloc[1:].iterrows())
    ]
    feature_collection = geojson.FeatureCollection(features)
    return geojson.dumps(feature_collection)


def make_geojson_line_segments_with_columns(
    time_series: pd.DataFrame, columns: Sequence[str]
) -> str:
    features = [
        geojson.Feature(
            geometry=geojson.LineString(
                coordinates=[
                    [row["longitude"], row["latitude"]],
                    [next_row["longitude"], next_row["latitude"]],
                ]
            ),
            properties={
                column: (
                    float(next_row[column])
                    if column in next_row and np.isfinite(next_row[column])
                    else None
                )
                for column in columns
            },
        )
        for _, group in time_series.groupby("segment_id")
        for (_, row), (_, next_row) in zip(group.iterrows(), group.iloc[1:].iterrows())
    ]
    feature_collection = geojson.FeatureCollection(features)
    return geojson.dumps(feature_collection)


def make_color_bar(time_series: pd.Series, format: str) -> dict[str, Any]:
    low, high, clamp_value = _make_value_clamp(time_series)
    cmap = matplotlib.colormaps["viridis"]
    colors = [
        (f"{value:{format}}", matplotlib.colors.to_hex(cmap(clamp_value(value))))
        for value in np.linspace(low, high, 10)
    ]
    return {"low": low, "high": high, "colors": colors}


def _make_value_clamp(values: pd.Series) -> tuple[float, float, Callable]:
    values_without_na = values.dropna()
    low = min(values_without_na)
    high = min(
        max(values_without_na),
        np.median(values_without_na) + 1.5 * inter_quartile_range(values_without_na),
    )
    return (
        low,
        high,
        lambda value: min(max((value - low) / (high - low + 1e-20), 0.0), 1.0),
    )


def _make_progress_marker_features(time_series: pd.DataFrame) -> list[geojson.Feature]:
    if time_series.empty:
        return []
    marker_points = _progress_marker_points(time_series)
    return [
        geojson.Feature(
            geometry=geojson.Point((point["longitude"], point["latitude"])),
            properties={"marker_progress": progress},
        )
        for progress in MARKER_PROGRESS_STOPS
        for point in [marker_points[progress]]
    ]


def _progress_marker_points(time_series: pd.DataFrame) -> dict[float, pd.Series]:
    if (
        "distance_km" not in time_series
        or (distance := pd.to_numeric(time_series["distance_km"], errors="coerce"))
        .isna()
        .all()
    ):
        final_index = len(time_series) - 1
        return {
            progress: time_series.iloc[int(round(final_index * progress))]
            for progress in MARKER_PROGRESS_STOPS
        }

    valid_rows = time_series.loc[distance.notna()]
    valid_distance = distance.loc[distance.notna()]
    start_distance = float(valid_distance.iloc[0])
    total_distance = float(valid_distance.iloc[-1] - start_distance)
    if total_distance <= 0:
        point = valid_rows.iloc[0]
        return {progress: point for progress in MARKER_PROGRESS_STOPS}

    result: dict[float, pd.Series] = {}
    for progress in MARKER_PROGRESS_STOPS:
        target_distance = start_distance + progress * total_distance
        nearest_index = (valid_distance - target_distance).abs().idxmin()
        result[progress] = time_series.loc[nearest_index]
    return result
