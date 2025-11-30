import geojson
import numpy as np

from .coordinates import get_distance
from .datamodel import Activity
from .datamodel import DB
from .datamodel import Segment
from .datamodel import SegmentMatch
from .tiles import compute_tile_float


def extract_segment_from_geojson(geojson_str: str) -> list[list[float]]:
    gj = geojson.loads(geojson_str)
    coordinates = gj["features"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coordinates]


def segment_track_distance(
    segment: Segment, activity: Activity
) -> tuple[float, np.ndarray]:
    """
    Computes asymmetric distance between a segment and a track in meters.

    It uses a one-sided Hausdorff distance. For every point in the segment, it computes the minimum distance to a point in the track. The maximum of these minimum distances is the result.

    Returns:

    """
    slat, slon = map(np.array, zip(*segment.coordinates))
    ts = activity.time_series
    tlat = ts["latitude"].to_numpy()
    tlon = ts["longitude"].to_numpy()
    d = get_distance(slat[:, None], slon[:, None], tlat[None, :], tlon[None, :])
    min_d = np.min(d, axis=1)
    index = np.argmin(d, axis=1)
    return np.max(min_d), index


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
    segment: Segment, activities_per_tile: dict[tuple[int, int], set[int]]
) -> None:
    segment_tiles = tiles_for_segment(segment, 17)
    activity_candidates = activity_candidates_for_tiles(
        segment_tiles, activities_per_tile
    )
    for activity_id in activity_candidates:
        activity = DB.session.get_one(Activity, activity_id)
        distance_m, index = segment_track_distance(segment, activity)
        print(f"{distance_m=}, {index=}")
        if distance_m < 20:
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
