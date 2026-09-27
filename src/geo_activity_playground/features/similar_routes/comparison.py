"""Asymmetric distances between two tracks.

Tracks are resampled to equidistant points so that the quantiles don't depend
on the recording interval or on pauses. Distances are measured from each point
to the nearest line segment of the reference track, so two tracks along the
same road have distance zero even if their points interleave.
"""

import dataclasses
from typing import Self

import numpy as np
import pandas as pd
import shapely

from ...core.tiles import compute_tile_float

EARTH_CIRCUMFERENCE_M = 40_075_016.686
RESAMPLING_STEP_M = 20.0
PREFILTER_MARGIN_M = 200.0


@dataclasses.dataclass
class ResampledTrack:
    """Points in Web Mercator units of the unit square."""

    points: np.ndarray
    meters_per_unit: np.ndarray
    segments: np.ndarray

    @classmethod
    def empty(cls) -> Self:
        return cls(np.empty((0, 2)), np.empty(0), np.empty((0, 2, 2)))

    @property
    def is_empty(self) -> bool:
        return len(self.points) == 0

    def bounds(self, margin_m: float) -> tuple[float, float, float, float]:
        margin = margin_m / self.meters_per_unit.min()
        x_min, y_min = self.points.min(axis=0) - margin
        x_max, y_max = self.points.max(axis=0) + margin
        return float(x_min), float(y_min), float(x_max), float(y_max)


def resample_track(time_series: pd.DataFrame) -> ResampledTrack:
    points = []
    segments = []
    for _, group in time_series.groupby("segment_id", sort=False):
        lat = group["latitude"].to_numpy()
        lon = group["longitude"].to_numpy()
        finite = np.isfinite(lat) & np.isfinite(lon)
        if not finite.any():
            continue
        x, y = compute_tile_float(lat[finite], lon[finite], 0)
        scale = _meters_per_unit(lat[finite])
        step_m = np.hypot(np.diff(x), np.diff(y)) * (scale[:-1] + scale[1:]) / 2
        arc_m = np.concatenate(([0.0], np.cumsum(step_m)))
        samples = np.arange(0.0, arc_m[-1], RESAMPLING_STEP_M)
        samples = np.append(samples, arc_m[-1])
        group_points = np.column_stack(
            (np.interp(samples, arc_m, x), np.interp(samples, arc_m, y))
        )
        points.append(group_points)
        if len(group_points) == 1:
            segments.append(np.stack((group_points, group_points), axis=1))
        else:
            segments.append(np.stack((group_points[:-1], group_points[1:]), axis=1))

    if not points:
        return ResampledTrack.empty()
    all_points = np.concatenate(points)
    return ResampledTrack(
        all_points,
        _meters_per_unit(_latitude_from_tile_y(all_points[:, 1])),
        np.concatenate(segments),
    )


def tracks_overlap(a: ResampledTrack, b: ResampledTrack) -> bool:
    if a.is_empty or b.is_empty:
        return False
    a_x_min, a_y_min, a_x_max, a_y_max = a.bounds(PREFILTER_MARGIN_M)
    b_x_min, b_y_min, b_x_max, b_y_max = b.bounds(PREFILTER_MARGIN_M)
    return (
        a_x_min <= b_x_max
        and b_x_min <= a_x_max
        and a_y_min <= b_y_max
        and b_y_min <= a_y_max
    )


def track_distance_quantiles(
    track: ResampledTrack, reference: ResampledTrack
) -> dict[str, float]:
    tree = shapely.STRtree(np.asarray(shapely.linestrings(reference.segments)))
    (point_index, _), distances = tree.query_nearest(
        shapely.points(track.points), return_distance=True, all_matches=False
    )
    distances_m = distances * track.meters_per_unit[point_index]
    p25, p50, p75, p95, p100 = np.quantile(distances_m, [0.25, 0.5, 0.75, 0.95, 1.0])
    return {
        "p25": float(p25),
        "p50": float(p50),
        "p75": float(p75),
        "p95": float(p95),
        "p100": float(p100),
        "mean": float(np.mean(distances_m)),
    }


def _meters_per_unit(lat: np.ndarray) -> np.ndarray:
    return EARTH_CIRCUMFERENCE_M * np.cos(np.radians(lat))


def _latitude_from_tile_y(y: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * y))))
