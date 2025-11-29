"""Segment matching algorithm for finding activities that pass through user-defined segments.

This module provides functionality to:
1. Find candidate activities using the quad tree (tile-based filtering)
2. Perform detailed geometric matching between segments and activity tracks
3. Determine entry/exit points and times for matched activities
"""

import logging
from typing import Iterator
from typing import Optional

import pandas as pd

from .coordinates import get_distance
from .datamodel import Activity
from .datamodel import DB
from .datamodel import Segment
from .datamodel import SegmentMatch
from .tiles import compute_tile

logger = logging.getLogger(__name__)

# Default tolerance for segment matching (meters)
DEFAULT_TOLERANCE_METERS = 50.0

# Zoom level for quad tree candidate filtering (~100m tiles at mid-latitudes)
CANDIDATE_FILTER_ZOOM = 18


def tiles_for_segment(
    coordinates: list[list[float]], zoom: int
) -> set[tuple[int, int]]:
    """Compute all tiles that a segment polyline passes through.

    Args:
        coordinates: List of [lon, lat] coordinate pairs (GeoJSON order)
        zoom: Tile zoom level

    Returns:
        Set of (tile_x, tile_y) tuples that the segment passes through
    """
    tiles: set[tuple[int, int]] = set()

    for i in range(len(coordinates)):
        lon, lat = coordinates[i]
        tile = compute_tile(lat, lon, zoom)
        tiles.add(tile)

        # Also add tiles along the line between consecutive points
        if i > 0:
            prev_lon, prev_lat = coordinates[i - 1]
            # Interpolate points along the line to catch all tiles
            line_tiles = _interpolate_line_tiles(prev_lat, prev_lon, lat, lon, zoom)
            tiles.update(line_tiles)

    return tiles


def _interpolate_line_tiles(
    lat1: float, lon1: float, lat2: float, lon2: float, zoom: int
) -> set[tuple[int, int]]:
    """Get all tiles that a line segment passes through."""
    tiles: set[tuple[int, int]] = set()

    # Calculate approximate distance and number of interpolation points
    dist = get_distance(lat1, lon1, lat2, lon2)
    # At zoom 18, tiles are roughly 100m at mid-latitudes
    tile_size_approx = 40000 / (2**zoom)  # rough meters per tile
    num_points = max(2, int(dist / (tile_size_approx / 4)) + 1)

    for i in range(num_points + 1):
        t = i / num_points
        lat = lat1 + t * (lat2 - lat1)
        lon = lon1 + t * (lon2 - lon1)
        tile = compute_tile(lat, lon, zoom)
        tiles.add(tile)

    return tiles


def get_candidate_activities(
    segment: Segment,
    activities_per_tile: dict[tuple[int, int], set[int]],
    zoom: int = CANDIDATE_FILTER_ZOOM,
) -> set[int]:
    """Find candidate activities that might match the segment using quad tree.

    This is a fast pre-filter using tile-based spatial indexing.

    Args:
        segment: The segment to match
        activities_per_tile: Mapping from tile to activity IDs (from TileState)
        zoom: Zoom level for tile lookup

    Returns:
        Set of activity IDs that pass through at least one segment tile
    """
    segment_tiles = tiles_for_segment(segment.coordinates, zoom)

    candidate_ids: set[int] = set()
    for tile in segment_tiles:
        if tile in activities_per_tile:
            candidate_ids.update(activities_per_tile[tile])

    return candidate_ids


def _point_to_line_segment_distance(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[float, float, float]:
    """Find the closest point on a line segment to a given point.

    Uses simple Euclidean projection (suitable for small distances).

    Args:
        px, py: The point to measure from
        x1, y1: Start of line segment
        x2, y2: End of line segment

    Returns:
        Tuple of (closest_x, closest_y, parameter_t) where t is in [0, 1]
        indicating position along the segment
    """
    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        # Degenerate case: segment is a point
        return x1, y1, 0.0

    # Parameter t for the closest point on the infinite line
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)

    # Clamp t to [0, 1] to stay on the segment
    t = max(0.0, min(1.0, t))

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return closest_x, closest_y, t


def _find_closest_point_on_activity(
    lat: float,
    lon: float,
    time_series: pd.DataFrame,
) -> tuple[int, float, float]:
    """Find the closest point on an activity track to a given coordinate.

    Args:
        lat, lon: The point to measure from
        time_series: Activity time series with 'latitude' and 'longitude' columns

    Returns:
        Tuple of (best_index, interpolated_lat, interpolated_lon)
        best_index is the index of the segment start point
    """
    lats = time_series["latitude"].values
    lons = time_series["longitude"].values

    best_dist = float("inf")
    best_index = 0
    best_lat = lats[0]
    best_lon = lons[0]

    for i in range(len(lats) - 1):
        # Find closest point on this line segment
        closest_lon, closest_lat, t = _point_to_line_segment_distance(
            lon, lat, lons[i], lats[i], lons[i + 1], lats[i + 1]
        )

        dist = get_distance(lat, lon, closest_lat, closest_lon)

        if dist < best_dist:
            best_dist = dist
            best_index = i
            best_lat = closest_lat
            best_lon = closest_lon

    return best_index, best_lat, best_lon


def match_segment_to_activity(
    segment: Segment,
    activity: Activity,
    time_series: pd.DataFrame,
    tolerance_meters: float = DEFAULT_TOLERANCE_METERS,
) -> Optional[SegmentMatch]:
    """Check if an activity matches a segment and find entry/exit points.

    The segment is considered matched if every point on the segment is within
    tolerance of the activity track (with interpolation).

    Args:
        segment: The segment to match
        activity: The activity to check
        time_series: Activity time series with latitude, longitude, time columns
        tolerance_meters: Maximum distance in meters for a point to be considered matching

    Returns:
        SegmentMatch instance if matched (not yet added to session), None otherwise
    """
    if len(time_series) < 2:
        return None

    coords = segment.coordinates
    if len(coords) < 2:
        return None

    # Check each segment point against the activity track
    indices_used: list[int] = []

    for coord in coords:
        lon, lat = coord
        idx, closest_lat, closest_lon = _find_closest_point_on_activity(
            lat, lon, time_series
        )
        dist = get_distance(lat, lon, closest_lat, closest_lon)

        if dist > tolerance_meters:
            # This segment point is too far from the activity
            return None

        indices_used.append(idx)

    # All segment points matched! Determine entry and exit
    entry_index = min(indices_used)
    exit_index = max(indices_used) + 1  # +1 to include the exit point

    # Ensure exit doesn't exceed bounds
    exit_index = min(exit_index, len(time_series) - 1)

    # Extract times
    entry_time = None
    exit_time = None
    duration = None

    if "time" in time_series.columns:
        entry_time_val = time_series.iloc[entry_index]["time"]
        exit_time_val = time_series.iloc[exit_index]["time"]

        if pd.notna(entry_time_val) and pd.notna(exit_time_val):
            entry_time = (
                entry_time_val.to_pydatetime()
                if hasattr(entry_time_val, "to_pydatetime")
                else entry_time_val
            )
            exit_time = (
                exit_time_val.to_pydatetime()
                if hasattr(exit_time_val, "to_pydatetime")
                else exit_time_val
            )
            duration = exit_time - entry_time

    # Calculate distance covered
    distance_km = None
    if "distance_km" in time_series.columns:
        entry_dist = time_series.iloc[entry_index]["distance_km"]
        exit_dist = time_series.iloc[exit_index]["distance_km"]
        if pd.notna(entry_dist) and pd.notna(exit_dist):
            distance_km = exit_dist - entry_dist

    return SegmentMatch(
        segment_id=segment.id,
        activity_id=activity.id,
        entry_index=entry_index,
        exit_index=exit_index,
        entry_time=entry_time,
        exit_time=exit_time,
        duration=duration,
        distance_km=distance_km,
    )


def match_segment_to_all_activities(
    segment: Segment,
    activities_per_tile: dict[tuple[int, int], set[int]],
    tolerance_meters: float = DEFAULT_TOLERANCE_METERS,
    zoom: int = CANDIDATE_FILTER_ZOOM,
) -> Iterator[SegmentMatch]:
    """Match a segment against all potentially matching activities.

    Args:
        segment: The segment to match
        activities_per_tile: Mapping from tile to activity IDs
        tolerance_meters: Maximum distance for matching
        zoom: Zoom level for candidate filtering

    Yields:
        SegmentMatch instances for each matched activity (not added to session)
    """
    candidate_ids = get_candidate_activities(segment, activities_per_tile, zoom)

    logger.info(
        f"Matching segment '{segment.name}' against {len(candidate_ids)} candidate activities"
    )

    for activity_id in candidate_ids:
        try:
            activity = DB.session.get_one(Activity, activity_id)
            time_series = activity.time_series

            if time_series is None or len(time_series) < 2:
                continue

            match = match_segment_to_activity(
                segment, activity, time_series, tolerance_meters
            )

            if match is not None:
                yield match
        except Exception as e:
            logger.warning(f"Error matching activity {activity_id}: {e}")
            continue


def match_new_segment_to_activities(
    segment: Segment,
    activities_per_tile: dict[tuple[int, int], set[int]],
    tolerance_meters: float = DEFAULT_TOLERANCE_METERS,
) -> int:
    """Match a newly created segment to all existing activities.

    Creates SegmentMatch records for all matching activities.

    Args:
        segment: The new segment
        activities_per_tile: Mapping from tile to activity IDs
        tolerance_meters: Maximum distance for matching

    Returns:
        Number of matches found
    """
    matches_found = 0

    for match in match_segment_to_all_activities(
        segment, activities_per_tile, tolerance_meters
    ):
        DB.session.add(match)
        matches_found += 1

    if matches_found > 0:
        DB.session.commit()
        logger.info(f"Created {matches_found} matches for segment '{segment.name}'")

    return matches_found


def match_new_activity_to_segments(
    activity: Activity,
    time_series: pd.DataFrame,
    tolerance_meters: float = DEFAULT_TOLERANCE_METERS,
) -> int:
    """Match a newly imported activity to all existing segments.

    Creates SegmentMatch records for all matching segments.

    Args:
        activity: The new activity
        time_series: The activity's time series data
        tolerance_meters: Maximum distance for matching

    Returns:
        Number of matches found
    """
    if time_series is None or len(time_series) < 2:
        return 0

    segments = DB.session.query(Segment).all()

    if not segments:
        return 0

    matches_found = 0

    for segment in segments:
        # Check if match already exists
        existing = (
            DB.session.query(SegmentMatch)
            .filter(
                SegmentMatch.segment_id == segment.id,
                SegmentMatch.activity_id == activity.id,
            )
            .first()
        )

        if existing:
            continue

        match = match_segment_to_activity(segment, activity, time_series, tolerance_meters)

        if match is not None:
            DB.session.add(match)
            matches_found += 1

    if matches_found > 0:
        DB.session.commit()
        logger.info(f"Activity '{activity.name}' matched {matches_found} segment(s)")

    return matches_found


def rematch_all_segments(
    activities_per_tile: dict[tuple[int, int], set[int]],
    tolerance_meters: float = DEFAULT_TOLERANCE_METERS,
) -> dict[int, int]:
    """Rematch all segments to all activities (useful after tolerance change).

    Clears existing matches and recreates them.

    Args:
        activities_per_tile: Mapping from tile to activity IDs
        tolerance_meters: Maximum distance for matching

    Returns:
        Dictionary mapping segment_id to number of matches
    """
    # Clear all existing matches
    DB.session.query(SegmentMatch).delete()
    DB.session.commit()

    segments = DB.session.query(Segment).all()
    results = {}

    for segment in segments:
        count = match_new_segment_to_activities(
            segment, activities_per_tile, tolerance_meters
        )
        results[segment.id] = count

    return results
