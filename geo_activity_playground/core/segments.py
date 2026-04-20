from collections.abc import Iterator

import geojson
import numpy as np
import sqlalchemy

from .config import Config
from .coordinates import get_distance
from .datamodel import DB, Activity, Segment, SegmentCheck, SegmentMatch
from .tiles import compute_tile_float


def extract_segment_from_geojson(geojson_str: str) -> list[list[float]]:
    gj = geojson.loads(geojson_str)
    coordinates = gj["features"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coordinates]


def segment_track_distance(
    segment: Segment, activity: Activity, config: Config
) -> Iterator[tuple[float, np.ndarray]]:
    """
    Computes asymmetric distance between a segment and a track in meters.

    It uses a one-sided Hausdorff distance. For every point in the segment, it
    computes the minimum distance to the track polyline (point-to-segment
    distance). The maximum of these minimum distances is the result.

    See docs/segment-matching.md for a more detailed explanation.
    """
    slat, slon = map(np.array, zip(*segment.coordinates))
    ts = activity.time_series
    tlat = ts["latitude"].to_numpy()
    tlon = ts["longitude"].to_numpy()

    close_d = _point_polyline_distance_m(tlat, tlon, slat, slon)
    close_mask = close_d < config.segment_split_distance

    padded = np.concatenate(([False], close_mask, [False]))
    mask_diff = np.diff(np.array(padded, dtype=np.int32))
    begins = np.where(mask_diff == 1)[0]
    ends = np.where(mask_diff == -1)[0]

    for begin, end in zip(begins, ends):
        if end - begin <= 0:
            continue

        tlat_slice = tlat[begin:end]
        tlon_slice = tlon[begin:end]
        min_d = _point_polyline_distance_m(slat, slon, tlat_slice, tlon_slice)

        d_slice = get_distance(
            slat[:, None], slon[:, None], tlat_slice[None, :], tlon_slice[None, :]
        )
        index = begin + np.argmin(d_slice, axis=1)
        yield float(np.max(min_d)), index


def _point_polyline_distance_m(
    point_lat: np.ndarray,
    point_lon: np.ndarray,
    line_lat: np.ndarray,
    line_lon: np.ndarray,
) -> np.ndarray:
    """
    Minimum distance in meters from points to a polyline.
    """
    if len(line_lat) == 0:
        return np.full(len(point_lat), np.inf)

    if len(line_lat) == 1:
        return get_distance(point_lat, point_lon, line_lat[0], line_lon[0])

    lat0 = float(np.mean(np.concatenate((point_lat, line_lat))))
    px, py = _latlon_to_local_xy_m(point_lat, point_lon, lat0)
    lx, ly = _latlon_to_local_xy_m(line_lat, line_lon, lat0)
    return _point_to_polyline_distance_xy(px, py, lx, ly)


def _latlon_to_local_xy_m(
    lat: np.ndarray, lon: np.ndarray, lat0_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    earth_radius = 6_371_000.0
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    lat0_rad = np.radians(lat0_deg)
    x = earth_radius * lon_rad * np.cos(lat0_rad)
    y = earth_radius * lat_rad
    return x, y


def _point_to_polyline_distance_xy(
    px: np.ndarray, py: np.ndarray, lx: np.ndarray, ly: np.ndarray
) -> np.ndarray:
    ax = lx[:-1][None, :]
    ay = ly[:-1][None, :]
    bx = lx[1:][None, :]
    by = ly[1:][None, :]

    vx = bx - ax
    vy = by - ay
    seg_len2 = np.maximum(vx * vx + vy * vy, 1e-12)

    wx = px[:, None] - ax
    wy = py[:, None] - ay
    t = np.clip((wx * vx + wy * vy) / seg_len2, 0.0, 1.0)

    cx = ax + t * vx
    cy = ay + t * vy
    dx = px[:, None] - cx
    dy = py[:, None] - cy
    return np.sqrt(np.min(dx * dx + dy * dy, axis=1))


def tiles_for_segment(segment: Segment, level: int) -> set[tuple[int, int]]:
    lat, lon = zip(*segment.coordinates)
    x, y = compute_tile_float(lat, lon, level)
    return {(int(a), int(b)) for a, b in zip(x, y)}


def activity_candidates_for_tiles(
    tiles: set[tuple[int, int]], activities_per_tile: dict[tuple[int, int], set[int]]
) -> set[int]:
    result: set[int] = set()
    for tile in tiles:
        result.update(activities_per_tile[tile])
    return result


def find_matches(
    segment: Segment,
    activities_per_tile: dict[tuple[int, int], set[int]],
    config: Config,
) -> None:
    segment_tiles = tiles_for_segment(segment, 17)
    activity_candidates = activity_candidates_for_tiles(
        segment_tiles, activities_per_tile
    )
    for activity_id in activity_candidates:
        activity = DB.session.get_one(Activity, activity_id)
        try_match_segment_activity(segment, activity, config)


def rematch_segment(
    segment: Segment,
    activities_per_tile: dict[tuple[int, int], set[int]],
    config: Config,
) -> tuple[int, int]:
    deleted_matches = DB.session.scalar(
        sqlalchemy.select(sqlalchemy.func.count(SegmentMatch.id)).where(
            SegmentMatch.segment_id == segment.id
        )
    )
    deleted_checks = DB.session.scalar(
        sqlalchemy.select(sqlalchemy.func.count(SegmentCheck.id)).where(
            SegmentCheck.segment_id == segment.id
        )
    )

    DB.session.execute(
        sqlalchemy.delete(SegmentMatch).where(SegmentMatch.segment_id == segment.id)
    )
    DB.session.execute(
        sqlalchemy.delete(SegmentCheck).where(SegmentCheck.segment_id == segment.id)
    )
    DB.session.commit()

    find_matches(segment, activities_per_tile, config)

    return int(deleted_matches or 0), int(deleted_checks or 0)


def try_match_segment_activity(
    segment: Segment, activity: Activity, config: Config
) -> None:
    if activity.start is None:
        return

    checks = DB.session.scalars(
        sqlalchemy.select(SegmentCheck).where(
            SegmentCheck.segment == segment, SegmentCheck.activity == activity
        )
    ).all()
    if checks:
        return

    segment_check = SegmentCheck(segment=segment, activity=activity)
    DB.session.add(segment_check)
    for distance_m, index in segment_track_distance(segment, activity, config):
        if distance_m < config.segment_max_distance:
            ts = activity.time_series
            i_entry = index[0]
            i_exit = index[-1]
            entry_time = ts["time"].iloc[i_entry]
            exit_time = ts["time"].iloc[i_exit]
            distance_km = (
                ts["distance_km"].iloc[i_exit] - ts["distance_km"].iloc[i_entry]
            )
            segment_match = SegmentMatch(
                segment=segment,
                activity=activity,
                entry_index=i_entry,
                entry_time=entry_time,
                exit_index=i_exit,
                exit_time=exit_time,
                duration=exit_time - entry_time,
                distance_km=distance_km,
            )
            DB.session.add(segment_match)
    DB.session.commit()
