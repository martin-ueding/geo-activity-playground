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
EIGHTH_MARKER_PROGRESS_STOPS: tuple[float, ...] = (0.125, 0.375, 0.625, 0.875)


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


def make_geojson_progress_markers_from_time_series(
    time_series: pd.DataFrame,
    eighth_marker_min_distance_km: float,
) -> str:
    feature_collection = geojson.FeatureCollection(
        _make_progress_marker_features(time_series, eighth_marker_min_distance_km)
    )
    return geojson.dumps(feature_collection)


def make_geojson_progress_markers_time_based(
    time_series: pd.DataFrame,
    eighth_marker_min_duration_s: float,
) -> str:
    feature_collection = geojson.FeatureCollection(
        _make_progress_marker_features_time(time_series, eighth_marker_min_duration_s)
    )
    return geojson.dumps(feature_collection)


def make_geojson_from_time_series(
    time_series: pd.DataFrame,
    eighth_marker_min_distance_km: float,
) -> str:
    features = []
    for _, group in time_series.groupby("segment_id"):
        features.append(
            geojson.LineString(
                [(lon, lat) for lat, lon in zip(group["latitude"], group["longitude"])]
            )
        )

    features.extend(
        _make_progress_marker_features(time_series, eighth_marker_min_distance_km)
    )

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


def _make_features_from_stops_and_points(
    stops: tuple[float, ...], marker_points: dict[float, pd.Series]
) -> list[geojson.Feature]:
    eighth_stops = set(EIGHTH_MARKER_PROGRESS_STOPS)
    return [
        geojson.Feature(
            geometry=geojson.Point((point["longitude"], point["latitude"])),
            properties={
                "marker_progress": progress,
                "marker_is_eighth": progress in eighth_stops,
            },
        )
        for progress in stops
        for point in [marker_points[progress]]
    ]


def _make_progress_marker_features(
    time_series: pd.DataFrame,
    eighth_marker_min_distance_km: float,
) -> list[geojson.Feature]:
    if time_series.empty:
        return []
    all_stops, _ = _progress_marker_stops_and_distance(
        time_series, eighth_marker_min_distance_km
    )
    marker_points = _progress_marker_points_from_metric(
        time_series,
        all_stops,
        pd.to_numeric(
            time_series.get("distance_km", pd.Series(dtype=float)), errors="coerce"
        ),
    )
    return _make_features_from_stops_and_points(all_stops, marker_points)


def _make_progress_marker_features_time(
    time_series: pd.DataFrame,
    eighth_marker_min_duration_s: float,
) -> list[geojson.Feature]:
    if time_series.empty:
        return []
    all_stops, _ = _progress_marker_stops_and_duration(
        time_series, eighth_marker_min_duration_s
    )
    if "time" not in time_series.columns:
        final_index = len(time_series) - 1
        marker_points = {
            p: time_series.iloc[int(round(final_index * p))] for p in all_stops
        }
    else:
        time_col = pd.to_datetime(time_series["time"], errors="coerce")
        elapsed = (time_col - time_col.iloc[0]).dt.total_seconds()
        marker_points = _progress_marker_points_from_metric(
            time_series, all_stops, elapsed
        )
    return _make_features_from_stops_and_points(all_stops, marker_points)


def _progress_marker_stops_and_distance(
    time_series: pd.DataFrame,
    eighth_marker_min_distance_km: float,
) -> tuple[tuple[float, ...], float]:
    if (
        "distance_km" not in time_series
        or (distance := pd.to_numeric(time_series["distance_km"], errors="coerce"))
        .isna()
        .all()
    ):
        return MARKER_PROGRESS_STOPS, 0.0
    valid_distance = distance.loc[distance.notna()]
    total_distance_km = float(valid_distance.iloc[-1] - valid_distance.iloc[0])
    if total_distance_km >= eighth_marker_min_distance_km:
        stops = tuple(
            sorted(set(MARKER_PROGRESS_STOPS) | set(EIGHTH_MARKER_PROGRESS_STOPS))
        )
        return stops, total_distance_km
    return MARKER_PROGRESS_STOPS, total_distance_km


def _progress_marker_stops_and_duration(
    time_series: pd.DataFrame,
    eighth_marker_min_duration_s: float,
) -> tuple[tuple[float, ...], float]:
    if "time" not in time_series.columns:
        return MARKER_PROGRESS_STOPS, 0.0
    time_col = pd.to_datetime(time_series["time"], errors="coerce").dropna()
    if len(time_col) < 2:
        return MARKER_PROGRESS_STOPS, 0.0
    duration_s = float((time_col.iloc[-1] - time_col.iloc[0]).total_seconds())
    if duration_s >= eighth_marker_min_duration_s:
        stops = tuple(
            sorted(set(MARKER_PROGRESS_STOPS) | set(EIGHTH_MARKER_PROGRESS_STOPS))
        )
        return stops, duration_s
    return MARKER_PROGRESS_STOPS, duration_s


def _progress_marker_points_from_metric(
    time_series: pd.DataFrame,
    stops: tuple[float, ...],
    metric: pd.Series,
) -> dict[float, pd.Series]:
    valid_mask = metric.notna()
    if not valid_mask.any():
        final_index = len(time_series) - 1
        return {
            progress: time_series.iloc[int(round(final_index * progress))]
            for progress in stops
        }
    valid_rows = time_series.loc[valid_mask]
    valid_metric = metric.loc[valid_mask]
    start = float(valid_metric.iloc[0])
    total = float(valid_metric.iloc[-1] - start)
    if total <= 0:
        point = valid_rows.iloc[0]
        return {progress: point for progress in stops}
    result: dict[float, pd.Series] = {}
    for progress in stops:
        target = start + progress * total
        nearest_index = (valid_metric - target).abs().idxmin()
        result[progress] = time_series.loc[nearest_index]
    return result
