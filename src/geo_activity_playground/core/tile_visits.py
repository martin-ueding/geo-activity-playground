import collections
import datetime
import logging
import zoneinfo
from collections.abc import Iterator
from typing import TypedDict

import pandas as pd
import sqlalchemy as sa
from tqdm import tqdm

from .activities import ActivityRepository
from .datamodel import DB, Activity, ActivityTile, TileVisit
from .tiles import interpolate_missing_tile

logger = logging.getLogger(__name__)


def get_first_visits_for_activity(
    activity_id: int, zoom: int | None = None
) -> list[TileVisit]:
    """Get all tiles that were first visited by the given activity.

    Args:
        activity_id: The activity ID to query for.
        zoom: Optional zoom level to filter by. If None, returns all zoom levels.

    Returns:
        List of TileVisit records where this activity was the first visitor.
    """
    query = DB.session.query(TileVisit).filter(
        TileVisit.first_activity_id == activity_id
    )
    if zoom is not None:
        query = query.filter(TileVisit.zoom == zoom)
    return query.all()


def get_tile_history_df(zoom: int) -> pd.DataFrame:
    """Get tile first visits as a DataFrame, ordered chronologically.

    This builds the DataFrame on-the-fly from the database, replacing
    the old tile_history pickle storage.

    Args:
        zoom: The zoom level to query for.

    Returns:
        DataFrame with columns: activity_id, time, tile_x, tile_y
    """
    visits = (
        DB.session.query(TileVisit)
        .filter(TileVisit.zoom == zoom)
        .order_by(
            TileVisit.first_time,
            TileVisit.first_activity_id,
            TileVisit.tile_x,
            TileVisit.tile_y,
        )
        .all()
    )

    if not visits:
        return pd.DataFrame(columns=["activity_id", "time", "tile_x", "tile_y"])

    return pd.DataFrame(
        {
            "activity_id": [v.first_activity_id for v in visits],
            "time": [
                pd.Timestamp(v.first_time) if v.first_time else pd.NaT for v in visits
            ],
            "tile_x": [v.tile_x for v in visits],
            "tile_y": [v.tile_y for v in visits],
        }
    )


def get_tile_count(zoom: int) -> int:
    """Get the count of explored tiles at a zoom level."""
    return DB.session.query(TileVisit).filter(TileVisit.zoom == zoom).count()


def get_tile_medians(zoom: int) -> tuple[int, int]:
    """Get the median tile_x and tile_y for centering the map.

    Returns:
        Tuple of (median_tile_x, median_tile_y)
    """
    from sqlalchemy import func

    result = (
        DB.session.query(func.avg(TileVisit.tile_x), func.avg(TileVisit.tile_y))
        .filter(TileVisit.zoom == zoom)
        .first()
    )

    if result and result[0] is not None:
        return (int(result[0]), int(result[1]))
    return (0, 0)


class TileInfo(TypedDict):
    visit_count: int
    first_time: pd.Timestamp
    first_id: int
    last_time: pd.Timestamp
    last_id: int


def remove_activity_from_tile_state(activity_id: int) -> int:
    removed_references = (
        DB.session.query(ActivityTile)
        .filter(ActivityTile.activity_id == activity_id)
        .delete()
    )
    DB.session.commit()
    return removed_references


def _consistency_check(repository: ActivityRepository) -> bool:
    present_activity_ids = set(repository.get_activity_ids())

    activity_tile_count = DB.session.query(ActivityTile).limit(1).count()
    tile_visit_count = DB.session.query(TileVisit).limit(1).count()
    if activity_tile_count == 0 and tile_visit_count > 0:
        logger.info(
            "activity_tile table is empty while tile visits exist; "
            "recomputing to populate it."
        )
        return False

    activity_tile_ids = {
        row[0] for row in DB.session.query(ActivityTile.activity_id).distinct()
    }
    deleted_activity_ids = activity_tile_ids - present_activity_ids
    if deleted_activity_ids:
        logger.info(f"Activities {deleted_activity_ids} have been deleted.")
        return False

    for first_activity_id, last_activity_id in DB.session.query(
        TileVisit.first_activity_id, TileVisit.last_activity_id
    ).all():
        if first_activity_id not in present_activity_ids:
            logger.info(f"Activity {first_activity_id} have been deleted.")
            return False
        if last_activity_id not in present_activity_ids:
            logger.info(f"Activity {last_activity_id} have been deleted.")
            return False

    missing_first_time_with_known_start = (
        DB.session.query(TileVisit.id)
        .join(Activity, TileVisit.first_activity_id == Activity.id)
        .filter(
            TileVisit.first_time.is_(None),
            Activity.start.is_not(None),
        )
        .limit(1)
        .first()
    )
    if missing_first_time_with_known_start is not None:
        logger.info(
            "Detected tile visits with NULL first_time despite first activity start time."
        )
        return False

    missing_last_time_with_known_start = (
        DB.session.query(TileVisit.id)
        .join(Activity, TileVisit.last_activity_id == Activity.id)
        .filter(
            TileVisit.last_time.is_(None),
            Activity.start.is_not(None),
        )
        .limit(1)
        .first()
    )
    if missing_last_time_with_known_start is not None:
        logger.info(
            "Detected tile visits with NULL last_time despite last activity start time."
        )
        return False

    return True


def _reset_tile_visits_db() -> None:
    """Clear all TileVisit and ActivityTile records from the database."""
    DB.session.query(TileVisit).delete()
    DB.session.query(ActivityTile).delete()
    DB.session.commit()
    logger.info("Cleared tile_visits and activity_tile tables in database.")


def refresh_tile_visits_for_activity(activity_id: int) -> None:
    """Incrementally repair tile visits after an activity's start time changed.

    Recomputes first/last visitor metadata for every tile the activity touches
    and rebuilds the cluster history for zoom levels whose first-visit ordering
    shifted.
    """
    affected_zooms: set[int] = set()

    zooms = [
        row[0]
        for row in DB.session.execute(
            sa.select(ActivityTile.zoom)
            .where(ActivityTile.activity_id == activity_id)
            .distinct()
        )
    ]

    for zoom in zooms:
        affected_tiles = [
            (row.tile_x, row.tile_y)
            for row in DB.session.execute(
                sa.select(ActivityTile.tile_x, ActivityTile.tile_y).where(
                    ActivityTile.zoom == zoom,
                    ActivityTile.activity_id == activity_id,
                )
            )
        ]
        if not affected_tiles:
            continue

        for chunk_start in range(0, len(affected_tiles), 400):
            chunk = affected_tiles[chunk_start : chunk_start + 400]

            visiting_by_tile: dict[tuple[int, int], set[int]] = collections.defaultdict(
                set
            )
            for row in DB.session.execute(
                sa.select(
                    ActivityTile.tile_x, ActivityTile.tile_y, ActivityTile.activity_id
                ).where(
                    ActivityTile.zoom == zoom,
                    sa.tuple_(ActivityTile.tile_x, ActivityTile.tile_y).in_(chunk),
                )
            ):
                visiting_by_tile[(row.tile_x, row.tile_y)].add(row.activity_id)

            relevant_activity_ids: set[int] = set()
            for ids in visiting_by_tile.values():
                relevant_activity_ids.update(ids)
            starts_by_id = {
                row.id: row.start
                for row in DB.session.execute(
                    sa.select(Activity.id, Activity.start).where(
                        Activity.id.in_(relevant_activity_ids)
                    )
                )
            }

            visits = {
                (visit.tile_x, visit.tile_y): visit
                for visit in DB.session.scalars(
                    sa.select(TileVisit).where(
                        TileVisit.zoom == zoom,
                        sa.tuple_(TileVisit.tile_x, TileVisit.tile_y).in_(chunk),
                    )
                )
            }

            for tile in chunk:
                visit = visits.get(tile)
                if visit is None:
                    continue
                visiting_ids = visiting_by_tile.get(tile, set())
                earliest_id: int | None = None
                earliest_time: datetime.datetime | None = None
                latest_id: int | None = None
                latest_time: datetime.datetime | None = None
                for vid in visiting_ids:
                    start = starts_by_id.get(vid)
                    if start is None:
                        continue
                    if earliest_time is None or start < earliest_time:
                        earliest_time = start
                        earliest_id = vid
                    if latest_time is None or start > latest_time:
                        latest_time = start
                        latest_id = vid

                if earliest_id is None:
                    # No visitor has a known start; keep the existing
                    # first/last activity ids and NULL times.
                    continue

                if (
                    visit.first_activity_id != earliest_id
                    or visit.first_time != earliest_time
                ):
                    affected_zooms.add(zoom)
                visit.first_activity_id = earliest_id
                visit.first_time = earliest_time
                visit.last_activity_id = latest_id
                visit.last_time = latest_time

        DB.session.commit()

    from ..features.explorer.clustering import rebuild_cluster_history_for_zoom

    for zoom in affected_zooms:
        rebuild_cluster_history_for_zoom(zoom, get_tile_history_df(zoom))


def _processed_activity_ids() -> set[int]:
    """Activity ids that already have tile membership in the database."""
    return {row[0] for row in DB.session.query(ActivityTile.activity_id).distinct()}


def compute_tile_visits_new(repository: ActivityRepository) -> None:
    if not _consistency_check(repository):
        logger.warning("Need to recompute Explorer Tiles.")
        _reset_tile_visits_db()

    processed_ids = _processed_activity_ids()
    unprocessed_ids = [
        activity_id
        for activity_id in repository.get_activity_ids()
        if activity_id not in processed_ids
    ]
    for activity_id in tqdm(unprocessed_ids, desc="Tile visits", delay=1):
        _process_activity(repository, activity_id)


def _process_activity(repository: ActivityRepository, activity_id: int) -> None:
    activity = repository.get_activity_by_id(activity_id)
    time_series = repository.get_time_series(activity_id)
    fallback_time = _fallback_timestamp_for_activity(activity)

    activity_tile_rows: list[ActivityTile] = []
    activity_tiles = pd.DataFrame(
        _tiles_from_points(time_series, 19), columns=["time", "tile_x", "tile_y"]
    )
    for zoom in reversed(range(20)):
        # Keep one row per tile while preferring entries with real timestamps.
        # This avoids freezing a tile's first/last time at NaT when the same
        # activity has a later point on the same tile with valid time data.
        activity_tiles = (
            activity_tiles.assign(
                _time_missing=activity_tiles["time"].isna(),
            )
            .sort_values(
                ["tile_x", "tile_y", "_time_missing", "time"],
                kind="stable",
            )
            .groupby(["tile_x", "tile_y"], sort=False)
            .head(1)
            .drop(columns="_time_missing")
        )
        tiles = list(zip(activity_tiles["tile_x"], activity_tiles["tile_y"]))
        existing_by_tile: dict[tuple[int, int], TileVisit] = {}
        for i in range(0, len(tiles), 400):
            chunk = tiles[i : i + 400]
            if not chunk:
                continue
            for visit in DB.session.scalars(
                sa.select(TileVisit).where(
                    TileVisit.zoom == zoom,
                    sa.tuple_(TileVisit.tile_x, TileVisit.tile_y).in_(chunk),
                )
            ):
                existing_by_tile[(visit.tile_x, visit.tile_y)] = visit

        for time, tile in zip(
            activity_tiles["time"],
            tiles,
        ):
            if activity.kind.consider_for_achievements:
                if pd.isna(time) and fallback_time is not None:
                    time = fallback_time
                if time is not None and time.tz is None:
                    time = time.tz_localize("UTC")
                has_time = pd.notna(time)
                db_time = time.to_pydatetime() if has_time else None
                existing = existing_by_tile.get(tile)
                if existing is None:
                    existing_by_tile[tile] = TileVisit(
                        zoom=zoom,
                        tile_x=tile[0],
                        tile_y=tile[1],
                        first_activity_id=activity_id,
                        first_time=db_time,
                        last_activity_id=activity_id,
                        last_time=db_time,
                        visit_count=1,
                    )
                    DB.session.add(existing_by_tile[tile])
                else:
                    existing.visit_count += 1
                    first_time = (
                        pd.Timestamp(existing.first_time)
                        if existing.first_time is not None
                        else None
                    )
                    last_time = (
                        pd.Timestamp(existing.last_time)
                        if existing.last_time is not None
                        else None
                    )
                    if first_time is not None and first_time.tz is None:
                        first_time = first_time.tz_localize("UTC")
                    if last_time is not None and last_time.tz is None:
                        last_time = last_time.tz_localize("UTC")
                    try:
                        if has_time:
                            if first_time is None or time < first_time:
                                existing.first_activity_id = activity_id
                                existing.first_time = db_time
                            if last_time is None or time > last_time:
                                existing.last_activity_id = activity_id
                                existing.last_time = db_time
                    except TypeError as e:
                        raise TypeError(
                            f"Mismatch in timezone awareness: {time=}, {first_time=}, {last_time=}"
                        ) from e

            activity_tile_rows.append(
                ActivityTile(
                    zoom=zoom,
                    tile_x=tile[0],
                    tile_y=tile[1],
                    activity_id=activity_id,
                )
            )

        if activity.kind.consider_for_achievements:
            DB.session.commit()

        # Move up one layer in the quad-tree.
        activity_tiles["tile_x"] //= 2
        activity_tiles["tile_y"] //= 2

    DB.session.add_all(activity_tile_rows)
    DB.session.commit()


def _fallback_timestamp_for_activity(activity: object) -> pd.Timestamp | None:
    start_utc = getattr(activity, "start_utc", None)
    if start_utc is None:
        start_utc = getattr(activity, "start", None)
    if start_utc is None:
        return None

    timestamp = pd.Timestamp(start_utc)
    if pd.isna(timestamp):
        return None
    if timestamp.tz is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp


def _tiles_from_points(
    time_series: pd.DataFrame, zoom: int
) -> Iterator[tuple[datetime.datetime, int, int]]:
    # XXX Some people haven't localized their time series yet. This breaks the tile history part. Just assume that it is UTC, should be good enough for tiles.
    if time_series["time"].dt.tz is None:
        time_series = time_series.copy()
        time_series["time"] = time_series["time"].dt.tz_localize(
            zoneinfo.ZoneInfo("UTC")
        )
    xf = time_series["x"] * 2**zoom
    yf = time_series["y"] * 2**zoom
    for t1, x1, y1, x2, y2, s1, s2 in zip(
        time_series["time"],
        xf,
        yf,
        xf.shift(1),
        yf.shift(1),
        time_series["segment_id"],
        time_series["segment_id"].shift(1),
    ):
        yield (t1, int(x1), int(y1))
        # We don't want to interpolate over segment boundaries.
        if s1 == s2:
            interpolated = interpolate_missing_tile(x1, y1, x2, y2)
            if interpolated is not None:
                yield (t1,) + interpolated


def get_activity_ids_in_tile(zoom: int, tile_x: int, tile_y: int) -> set[int]:
    """Activity ids passing through a single tile."""
    return {
        row[0]
        for row in DB.session.execute(
            sa.select(ActivityTile.activity_id).where(
                ActivityTile.zoom == zoom,
                ActivityTile.tile_x == tile_x,
                ActivityTile.tile_y == tile_y,
            )
        )
    }


def get_activity_ids_in_bounds(
    zoom: int, x_min: int, x_max: int, y_min: int, y_max: int
) -> set[int]:
    """Activity ids passing through any tile within a viewport."""
    return {
        row[0]
        for row in DB.session.execute(
            sa.select(ActivityTile.activity_id).where(
                ActivityTile.zoom == zoom,
                ActivityTile.tile_x >= x_min,
                ActivityTile.tile_x <= x_max,
                ActivityTile.tile_y >= y_min,
                ActivityTile.tile_y <= y_max,
            )
        )
    }


def get_activity_ids_in_tiles(zoom: int, tiles: Iterator[tuple[int, int]]) -> set[int]:
    """Activity ids passing through any of the given tiles."""
    tile_list = list(tiles)
    result: set[int] = set()
    for chunk_start in range(0, len(tile_list), 400):
        chunk = tile_list[chunk_start : chunk_start + 400]
        for row in DB.session.execute(
            sa.select(ActivityTile.activity_id).where(
                ActivityTile.zoom == zoom,
                sa.tuple_(ActivityTile.tile_x, ActivityTile.tile_y).in_(chunk),
            )
        ):
            result.add(row[0])
    return result


def get_tile_visits_in_bounds(
    zoom: int, x_min: int, x_max: int, y_min: int, y_max: int
) -> dict[tuple[int, int], TileInfo]:
    """Return tile visit info for tiles within a viewport, read from the database."""
    rows = DB.session.execute(
        sa.select(
            TileVisit.tile_x,
            TileVisit.tile_y,
            TileVisit.visit_count,
            TileVisit.first_activity_id,
            TileVisit.first_time,
            TileVisit.last_activity_id,
            TileVisit.last_time,
        ).where(
            TileVisit.zoom == zoom,
            TileVisit.tile_x >= x_min,
            TileVisit.tile_x <= x_max,
            TileVisit.tile_y >= y_min,
            TileVisit.tile_y <= y_max,
        )
    ).all()

    # Older rows may have NULL first_time/last_time; fall back to the
    # relevant activity's start time, matching _process_activity's behavior.
    fallback_activity_ids = {
        row.first_activity_id for row in rows if row.first_time is None
    } | {row.last_activity_id for row in rows if row.last_time is None}
    fallback_starts: dict[int, datetime.datetime] = {}
    if fallback_activity_ids:
        fallback_starts = dict(
            DB.session.execute(
                sa.select(Activity.id, Activity.start).where(
                    Activity.id.in_(fallback_activity_ids)
                )
            ).all()
        )

    def _timestamp(time: datetime.datetime | None, activity_id: int) -> pd.Timestamp:
        if time is not None:
            return pd.Timestamp(time)
        fallback = fallback_starts.get(activity_id)
        return pd.Timestamp(fallback) if fallback is not None else pd.NaT

    return {
        (row.tile_x, row.tile_y): {
            "visit_count": row.visit_count,
            "first_time": _timestamp(row.first_time, row.first_activity_id),
            "first_id": row.first_activity_id,
            "last_time": _timestamp(row.last_time, row.last_activity_id),
            "last_id": row.last_activity_id,
        }
        for row in rows
    }
