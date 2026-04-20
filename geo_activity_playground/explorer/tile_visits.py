import collections
import datetime
import functools
import itertools
import json
import logging
import pathlib
import pickle
import zoneinfo
from collections.abc import Iterator
from typing import TypedDict

import pandas as pd
import sqlalchemy as sa
from tqdm import tqdm

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.datamodel import (
    DB,
    ClusterHistoryCheckpoint,
    ClusterHistoryEvent,
    TileVisit,
)
from ..core.paths import atomic_open
from ..core.tasks import WorkTracker, try_load_pickle, work_tracker_path
from ..core.tiles import adjacent_to, interpolate_missing_tile

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


class TileEvolutionState:
    def __init__(self) -> None:
        self.num_neighbors: dict[tuple[int, int], int] = {}
        "Mapping from tile to the number of its neighbors."

        self.memberships: dict[tuple[int, int], tuple[int, int]] = {}
        "Mapping from tile to the representative tile."
        self.clusters: dict[tuple[int, int], list[tuple[int, int]]] = {}
        "Mapping from representative tile to the list of all cluster members."

        self.cluster_evolution = pd.DataFrame()
        self.square_start = 0
        self.cluster_start = 0
        self.max_square_size = 0
        self.visited_tiles: set[tuple[int, int]] = set()
        self.square_evolution = pd.DataFrame()
        self.square_x: int | None = None
        self.square_y: int | None = None


class ClusterReplayState:
    def __init__(self) -> None:
        self.visited_tiles: set[tuple[int, int]] = set()
        self.neighbor_counts: dict[tuple[int, int], int] = {}
        self.cluster_tiles: set[tuple[int, int]] = set()
        self.parents: dict[tuple[int, int], tuple[int, int]] = {}
        self.component_sizes: dict[tuple[int, int], int] = {}
        self.max_cluster_size = 0


CLUSTER_CHECKPOINT_INTERVAL = 1_000


def _find_root(
    parents: dict[tuple[int, int], tuple[int, int]], tile: tuple[int, int]
) -> tuple[int, int]:
    root = tile
    while parents[root] != root:
        root = parents[root]
    while parents[tile] != tile:
        parent = parents[tile]
        parents[tile] = root
        tile = parent
    return root


def _union_roots(
    state: ClusterReplayState,
    left: tuple[int, int],
    right: tuple[int, int],
) -> None:
    left_root = _find_root(state.parents, left)
    right_root = _find_root(state.parents, right)
    if left_root == right_root:
        return
    if state.component_sizes[left_root] < state.component_sizes[right_root]:
        left_root, right_root = right_root, left_root
    state.parents[right_root] = left_root
    state.component_sizes[left_root] += state.component_sizes[right_root]
    del state.component_sizes[right_root]
    if state.component_sizes[left_root] > state.max_cluster_size:
        state.max_cluster_size = state.component_sizes[left_root]


def _activate_cluster_tile(state: ClusterReplayState, tile: tuple[int, int]) -> None:
    if tile in state.cluster_tiles:
        return
    state.cluster_tiles.add(tile)
    state.parents[tile] = tile
    state.component_sizes[tile] = 1
    if state.max_cluster_size < 1:
        state.max_cluster_size = 1
    for other in adjacent_to(tile):
        if other in state.cluster_tiles:
            _union_roots(state, tile, other)


def apply_cluster_history_event(
    state: ClusterReplayState, tile: tuple[int, int]
) -> int | None:
    if tile in state.visited_tiles:
        return None
    previous_max = state.max_cluster_size
    state.visited_tiles.add(tile)
    state.neighbor_counts.setdefault(tile, 0)

    for other in adjacent_to(tile):
        if other in state.visited_tiles:
            state.neighbor_counts[tile] += 1
            state.neighbor_counts[other] = state.neighbor_counts.get(other, 0) + 1
            if state.neighbor_counts[other] == 4:
                _activate_cluster_tile(state, other)

    if state.neighbor_counts[tile] == 4:
        _activate_cluster_tile(state, tile)

    if state.max_cluster_size > previous_max:
        return state.max_cluster_size
    return None


def _state_to_payload(state: ClusterReplayState) -> str:
    payload = {
        "visited_tiles": [list(tile) for tile in sorted(state.visited_tiles)],
        "neighbor_counts": [
            [tile[0], tile[1], count]
            for tile, count in sorted(state.neighbor_counts.items())
        ],
        "cluster_tiles": [list(tile) for tile in sorted(state.cluster_tiles)],
        "parents": [
            [tile[0], tile[1], parent[0], parent[1]]
            for tile, parent in sorted(state.parents.items())
        ],
        "component_sizes": [
            [tile[0], tile[1], size]
            for tile, size in sorted(state.component_sizes.items())
        ],
        "max_cluster_size": state.max_cluster_size,
    }
    return json.dumps(payload, separators=(",", ":"))


def _state_from_payload(payload_json: str) -> ClusterReplayState:
    raw = json.loads(payload_json)
    state = ClusterReplayState()
    state.visited_tiles = {tuple(tile) for tile in raw.get("visited_tiles", [])}
    state.neighbor_counts = {
        (entry[0], entry[1]): entry[2] for entry in raw.get("neighbor_counts", [])
    }
    state.cluster_tiles = {tuple(tile) for tile in raw.get("cluster_tiles", [])}
    state.parents = {
        (entry[0], entry[1]): (entry[2], entry[3]) for entry in raw.get("parents", [])
    }
    state.component_sizes = {
        (entry[0], entry[1]): entry[2] for entry in raw.get("component_sizes", [])
    }
    state.max_cluster_size = raw.get("max_cluster_size", 0)
    return state


class TileState(TypedDict):
    activities_per_tile: dict[int, dict[tuple[int, int], set[int]]]
    evolution_state: dict[int, TileEvolutionState]
    version: int


# Version 4: Removed duplicate tile_visits from pickle
TILE_STATE_VERSION = 4


class TileVisitAccessor:
    PATH = pathlib.Path("Cache/tile-state-3.pickle")
    OLD_PATH = pathlib.Path("Cache/tile-state-2.pickle")

    def __init__(self) -> None:
        loaded_state: dict | None = try_load_pickle(self.PATH)
        self.tile_state: TileState | None = None
        self._pending_migration: dict | None = None

        if loaded_state is None:
            # Try loading old pickle - defer DB migration until we have app context
            old_state = try_load_pickle(self.OLD_PATH)
            if old_state is not None:
                logger.info("Found old tile-state-2.pickle, will migrate to v3...")
                self.tile_state = _normalize_tile_state(old_state)
                # Store old state for DB migration later (needs app context)
                self._pending_migration = old_state
                self.save()
            else:
                self.tile_state = make_tile_state()
        else:
            self.tile_state = _normalize_tile_state(loaded_state)
            if (
                loaded_state.get("version", None) != TILE_STATE_VERSION
                or "tile_visits" in loaded_state
            ):
                self.save()

    def complete_migration(self) -> None:
        """Complete pending migration to database. Must be called with app context."""
        if self._pending_migration is not None:
            logger.info("Completing tile_history migration to database...")
            _migrate_from_pickle_to_db(self._pending_migration)
            self._pending_migration = None
            logger.info("Migration complete.")

    def reset(self) -> None:
        self.tile_state = make_tile_state()

    def save(self) -> None:
        with atomic_open(self.PATH, "wb") as f:
            pickle.dump(self.tile_state, f)


def make_defaultdict_dict():
    return collections.defaultdict(dict)


def make_defaultdict_set():
    return collections.defaultdict(set)


def make_tile_state() -> TileState:
    tile_state: TileState = {
        "activities_per_tile": collections.defaultdict(make_defaultdict_set),
        "evolution_state": collections.defaultdict(TileEvolutionState),
        "version": TILE_STATE_VERSION,
    }
    return tile_state


def _normalize_tile_state(raw_state: dict) -> TileState:
    tile_state = make_tile_state()
    if "activities_per_tile" in raw_state:
        tile_state["activities_per_tile"] = raw_state["activities_per_tile"]
    if "evolution_state" in raw_state:
        tile_state["evolution_state"] = raw_state["evolution_state"]
    return tile_state


def remove_activity_from_tile_state(tile_state: TileState, activity_id: int) -> int:
    removed_references = 0
    for activities_per_tile in tile_state["activities_per_tile"].values():
        empty_tiles: list[tuple[int, int]] = []
        for tile, tile_activity_ids in activities_per_tile.items():
            if activity_id not in tile_activity_ids:
                continue
            tile_activity_ids.discard(activity_id)
            removed_references += 1
            if not tile_activity_ids:
                empty_tiles.append(tile)
        for tile in empty_tiles:
            del activities_per_tile[tile]
    return removed_references


def _consistency_check(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> bool:
    present_activity_ids = set(repository.get_activity_ids())

    for _zoom, activities_per_tile in tile_visit_accessor.tile_state[
        "activities_per_tile"
    ].items():
        for _tile, tile_activity_ids in activities_per_tile.items():
            deleted_activity_ids = tile_activity_ids - present_activity_ids
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

    return True


def _reset_tile_visits_db() -> None:
    """Clear all TileVisit records from the database."""
    DB.session.query(TileVisit).delete()
    DB.session.commit()
    invalidate_tile_visits_cache()
    logger.info("Cleared tile_visits table in database.")


def _migrate_from_pickle_to_db(old_tile_state: dict) -> None:
    """Migrate existing pickle data to the TileVisit database table.

    This migrates from older pickle formats (v2/v3) that had tile_history
    or tile_visits with activity_ids sets.
    """
    # Check if DB already has data
    existing_count = DB.session.query(TileVisit).limit(1).count()
    if existing_count > 0:
        return  # Already migrated

    # Try to migrate from tile_visits in pickle (has first/last info)
    tile_visits = old_tile_state.get("tile_visits", {})
    if tile_visits:
        total_tiles = sum(len(visits) for visits in tile_visits.values())
        if total_tiles > 0:
            logger.info(f"Migrating {total_tiles} tiles from pickle to database...")
            for zoom, visits_at_zoom in tile_visits.items():
                batch: list[TileVisit] = []
                for (tile_x, tile_y), info in visits_at_zoom.items():
                    first_time = info.get("first_time")
                    last_time = info.get("last_time")
                    db_first_time = (
                        first_time.to_pydatetime() if pd.notna(first_time) else None
                    )
                    db_last_time = (
                        last_time.to_pydatetime() if pd.notna(last_time) else None
                    )

                    # Get visit count from activity_ids if present, otherwise from visit_count
                    if "activity_ids" in info:
                        visit_count = len(info["activity_ids"])
                    else:
                        visit_count = info.get("visit_count", 1)

                    batch.append(
                        TileVisit(
                            zoom=zoom,
                            tile_x=tile_x,
                            tile_y=tile_y,
                            first_activity_id=info["first_id"],
                            first_time=db_first_time,
                            last_activity_id=info["last_id"],
                            last_time=db_last_time,
                            visit_count=visit_count,
                        )
                    )

                    if len(batch) >= 1000:
                        DB.session.add_all(batch)
                        DB.session.commit()
                        batch = []

                if batch:
                    DB.session.add_all(batch)
                    DB.session.commit()

            logger.info("Migration complete.")
            return

    # Fallback: migrate from tile_history (older format)
    tile_history = old_tile_state.get("tile_history", {})
    if not tile_history:
        return

    total_records = sum(
        len(df) for df in tile_history.values() if isinstance(df, pd.DataFrame)
    )
    if total_records == 0:
        return

    logger.info(
        f"Migrating {total_records} tile first visits from pickle to database..."
    )

    for zoom, tile_history_df in tile_history.items():
        if not isinstance(tile_history_df, pd.DataFrame) or tile_history_df.empty:
            continue

        history_batch: list[TileVisit] = []
        for _, row in tile_history_df.iterrows():
            time = row["time"]
            db_time = time.to_pydatetime() if pd.notna(time) else None
            activity_id = int(row["activity_id"])
            history_batch.append(
                TileVisit(
                    zoom=zoom,
                    tile_x=int(row["tile_x"]),
                    tile_y=int(row["tile_y"]),
                    first_activity_id=activity_id,
                    first_time=db_time,
                    last_activity_id=activity_id,
                    last_time=db_time,
                    visit_count=1,
                )
            )

            if len(history_batch) >= 1000:
                DB.session.add_all(history_batch)
                DB.session.commit()
                history_batch = []

        if history_batch:
            DB.session.add_all(history_batch)
            DB.session.commit()

    logger.info("Migration complete.")


def compute_tile_visits_new(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> None:
    work_tracker = WorkTracker(work_tracker_path("tile-state"))

    # Complete any pending migration from old pickle format (requires app context)
    tile_visit_accessor.complete_migration()

    if not _consistency_check(repository, tile_visit_accessor):
        logger.warning("Need to recompute Explorer Tiles due to deleted activities.")
        tile_visit_accessor.reset()
        _reset_tile_visits_db()
        work_tracker.reset()

    for activity_id in tqdm(
        work_tracker.filter(repository.get_activity_ids()), desc="Tile visits", delay=1
    ):
        _process_activity(repository, tile_visit_accessor.tile_state, activity_id)
        work_tracker.mark_done(activity_id)

    invalidate_tile_visits_cache()
    tile_visit_accessor.save()
    work_tracker.close()


def _process_activity(
    repository: ActivityRepository, tile_state: TileState, activity_id: int
) -> None:
    activity = repository.get_activity_by_id(activity_id)
    time_series = repository.get_time_series(activity_id)

    activity_tiles = pd.DataFrame(
        _tiles_from_points(time_series, 19), columns=["time", "tile_x", "tile_y"]
    )
    for zoom in reversed(range(20)):
        activities_per_tile = tile_state["activities_per_tile"][zoom]
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

            activities_per_tile[tile].add(activity_id)

        if activity.kind.consider_for_achievements:
            DB.session.commit()
            invalidate_tile_visits_cache()

        # Move up one layer in the quad-tree.
        activity_tiles["tile_x"] //= 2
        activity_tiles["tile_y"] //= 2


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


def compute_tile_evolution(tile_state: TileState, config: Config) -> None:
    for zoom in config.explorer_zoom_levels:
        # Get tile history from database
        tile_history = get_tile_history_df(zoom)
        rebuild_cluster_history_for_zoom(zoom, tile_history)
        _compute_cluster_evolution(
            tile_history,
            tile_state["evolution_state"][zoom],
            zoom,
        )
        _compute_square_history(
            tile_history,
            tile_state["evolution_state"][zoom],
            zoom,
        )


def rebuild_cluster_history_for_zoom(zoom: int, tile_history: pd.DataFrame) -> None:
    DB.session.query(ClusterHistoryEvent).filter(
        ClusterHistoryEvent.zoom == zoom
    ).delete()
    DB.session.query(ClusterHistoryCheckpoint).filter(
        ClusterHistoryCheckpoint.zoom == zoom
    ).delete()

    state = ClusterReplayState()
    event_batch: list[ClusterHistoryEvent] = []
    checkpoint_batch: list[ClusterHistoryCheckpoint] = []

    for event_index, row in enumerate(tile_history.itertuples(index=False), start=1):
        tile = (int(row.tile_x), int(row.tile_y))
        event_batch.append(
            ClusterHistoryEvent(
                zoom=zoom,
                event_index=event_index,
                activity_id=int(row.activity_id),
                time=(row.time.to_pydatetime() if pd.notna(row.time) else None),
                tile_x=tile[0],
                tile_y=tile[1],
            )
        )

        apply_cluster_history_event(state, tile)

        if event_index % CLUSTER_CHECKPOINT_INTERVAL == 0:
            checkpoint_batch.append(
                ClusterHistoryCheckpoint(
                    zoom=zoom,
                    event_index=event_index,
                    time=(row.time.to_pydatetime() if pd.notna(row.time) else None),
                    max_cluster_size=state.max_cluster_size,
                    payload_json=_state_to_payload(state),
                )
            )

        if len(event_batch) >= 1_000:
            DB.session.add_all(event_batch)
            event_batch = []
        if len(checkpoint_batch) >= 50:
            DB.session.add_all(checkpoint_batch)
            checkpoint_batch = []

    if event_batch:
        DB.session.add_all(event_batch)
    if len(tile_history) > 0 and len(tile_history) % CLUSTER_CHECKPOINT_INTERVAL != 0:
        last = tile_history.iloc[-1]
        checkpoint_batch.append(
            ClusterHistoryCheckpoint(
                zoom=zoom,
                event_index=len(tile_history),
                time=(last["time"].to_pydatetime() if pd.notna(last["time"]) else None),
                max_cluster_size=state.max_cluster_size,
                payload_json=_state_to_payload(state),
            )
        )
    if checkpoint_batch:
        DB.session.add_all(checkpoint_batch)

    DB.session.commit()


def get_cluster_history_cutoff_for_activity(
    zoom: int, activity_id: int
) -> tuple[int | None, int | None]:
    first_event = DB.session.scalar(
        sa.select(sa.func.min(ClusterHistoryEvent.event_index)).where(
            ClusterHistoryEvent.zoom == zoom,
            ClusterHistoryEvent.activity_id == activity_id,
        )
    )
    last_event = DB.session.scalar(
        sa.select(sa.func.max(ClusterHistoryEvent.event_index)).where(
            ClusterHistoryEvent.zoom == zoom,
            ClusterHistoryEvent.activity_id == activity_id,
        )
    )
    if first_event is None or last_event is None:
        return None, None
    return int(first_event), int(last_event)


def get_cluster_history_latest_event_index(zoom: int) -> int:
    latest = DB.session.scalar(
        sa.select(sa.func.max(ClusterHistoryEvent.event_index)).where(
            ClusterHistoryEvent.zoom == zoom
        )
    )
    return int(latest or 0)


def get_cluster_tiles_at_cutoff(zoom: int, event_index: int) -> set[tuple[int, int]]:
    return set(get_cluster_state_at_cutoff(zoom, event_index).cluster_tiles)


def get_cluster_state_at_cutoff(zoom: int, event_index: int) -> ClusterReplayState:
    if event_index <= 0:
        return ClusterReplayState()

    checkpoint = DB.session.scalar(
        sa.select(ClusterHistoryCheckpoint)
        .where(
            ClusterHistoryCheckpoint.zoom == zoom,
            ClusterHistoryCheckpoint.event_index <= event_index,
        )
        .order_by(ClusterHistoryCheckpoint.event_index.desc())
        .limit(1)
    )
    if checkpoint is None:
        state = ClusterReplayState()
        start_event_index = 0
    else:
        state = _state_from_payload(checkpoint.payload_json)
        start_event_index = checkpoint.event_index

    events = DB.session.scalars(
        sa.select(ClusterHistoryEvent)
        .where(
            ClusterHistoryEvent.zoom == zoom,
            ClusterHistoryEvent.event_index > start_event_index,
            ClusterHistoryEvent.event_index <= event_index,
        )
        .order_by(ClusterHistoryEvent.event_index)
    ).all()
    for event in events:
        apply_cluster_history_event(state, (event.tile_x, event.tile_y))
    return state


def get_cluster_tile_diff_for_activity(
    zoom: int, activity_id: int
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    first_event, last_event = get_cluster_history_cutoff_for_activity(zoom, activity_id)
    if first_event is None or last_event is None:
        return set(), set()
    before = get_cluster_tiles_at_cutoff(zoom, first_event - 1)
    after = get_cluster_tiles_at_cutoff(zoom, last_event)
    return after - before, before - after


def get_cluster_tile_activations_df(zoom: int) -> pd.DataFrame:
    events = DB.session.scalars(
        sa.select(ClusterHistoryEvent)
        .where(ClusterHistoryEvent.zoom == zoom)
        .order_by(ClusterHistoryEvent.event_index)
    ).all()
    if not events:
        return pd.DataFrame(
            columns=["time", "event_index", "activity_id", "tile_x", "tile_y"]
        )

    state = ClusterReplayState()
    rows: list[dict[str, object]] = []
    for event in events:
        event_tile = (event.tile_x, event.tile_y)
        candidates = [event_tile, *adjacent_to(event_tile)]
        active_before = {tile for tile in candidates if tile in state.cluster_tiles}
        apply_cluster_history_event(state, event_tile)
        for tile in candidates:
            if tile in active_before or tile not in state.cluster_tiles:
                continue
            rows.append(
                {
                    "time": pd.Timestamp(event.time)
                    if event.time is not None
                    else pd.NaT,
                    "event_index": event.event_index,
                    "activity_id": event.activity_id,
                    "tile_x": tile[0],
                    "tile_y": tile[1],
                }
            )
    return pd.DataFrame(rows)


def _compute_cluster_evolution(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    if len(s.cluster_evolution) > 0:
        max_cluster_so_far = s.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_so_far = 0

    rows = []
    for _index, row in tqdm(
        tiles.iterrows(),
        desc=f"Cluster evolution for {zoom=}",
        delay=1,
    ):
        new_clusters = False
        # Current tile.
        tile = (row["tile_x"], row["tile_y"])

        if tile in s.num_neighbors:
            continue

        # This tile is new, therefore it doesn't have an entries in the neighbor list yet.
        s.num_neighbors[tile] = 0

        # Go through the adjacent tile and check whether there are neighbors.
        for other in adjacent_to(tile):
            if other in s.num_neighbors:
                # The other tile is already visited. That means that the current tile has a neighbor.
                s.num_neighbors[tile] += 1
                # Alto the other tile has gained a neighbor.
                s.num_neighbors[other] += 1

        # If the current tile has all neighbors, make it it's own cluster.
        if s.num_neighbors[tile] == 4:
            s.clusters[tile] = [tile]
            s.memberships[tile] = tile

        # Also make the adjacent tiles their own clusters, if they are full.
        this_and_neighbors = [tile] + list(adjacent_to(tile))
        for other in this_and_neighbors:
            if s.num_neighbors.get(other, 0) == 4:
                s.clusters[other] = [other]
                s.memberships[other] = other

        for candidate in this_and_neighbors:
            # If the the candidate is not a cluster tile, skip.
            if candidate not in s.memberships:
                continue
            # The candidate is a cluster tile. Let's see whether any of the neighbors are also cluster tiles but with a different cluster. Then we need to join them.
            for other in adjacent_to(candidate):
                if other not in s.memberships:
                    continue
                # The other tile is also a cluster tile.
                if s.memberships[candidate] == s.memberships[other]:
                    continue
                # The two clusters are not the same. We add the other's cluster tile to this tile.
                this_cluster = s.clusters[s.memberships[candidate]]
                assert isinstance(other, tuple), other
                assert isinstance(s.memberships[other], tuple), s.memberships[other]
                other_cluster = s.clusters[s.memberships[other]]
                other_cluster_name = s.memberships[other]
                this_cluster.extend(other_cluster)
                # Update the other cluster tiles that they now point to the new cluster. This also updates the other tile.
                for member in other_cluster:
                    s.memberships[member] = s.memberships[candidate]
                del s.clusters[other_cluster_name]
                new_clusters = True

        if new_clusters:
            max_cluster_size = max(
                (len(members) for members in s.clusters.values()),
                default=0,
            )
            if max_cluster_size > max_cluster_so_far:
                rows.append(
                    {
                        "time": row["time"],
                        "max_cluster_size": max_cluster_size,
                    }
                )
                max_cluster_so_far = max_cluster_size

    new_cluster_evolution = pd.DataFrame(rows)
    s.cluster_evolution = pd.concat([s.cluster_evolution, new_cluster_evolution])
    s.cluster_start = len(tiles)


@functools.lru_cache(maxsize=64)
def get_tile_visits(zoom: int) -> dict[tuple[int, int], TileInfo]:
    visits = DB.session.scalars(
        sa.select(TileVisit).where(TileVisit.zoom == zoom)
    ).all()
    return {
        (visit.tile_x, visit.tile_y): {
            "visit_count": visit.visit_count,
            "first_time": (
                pd.Timestamp(visit.first_time) if visit.first_time else pd.NaT
            ),
            "first_id": visit.first_activity_id,
            "last_time": pd.Timestamp(visit.last_time) if visit.last_time else pd.NaT,
            "last_id": visit.last_activity_id,
        }
        for visit in visits
    }


def invalidate_tile_visits_cache() -> None:
    get_tile_visits.cache_clear()


def _compute_square_history(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    rows = []
    for _index, row in tqdm(
        tiles.iterrows(),
        desc=f"Square evolution for {zoom=}",
        delay=1,
    ):
        tile = (row["tile_x"], row["tile_y"])
        if tile in s.visited_tiles:
            continue
        x, y = tile
        s.visited_tiles.add(tile)
        for square_size in itertools.count(s.max_square_size + 1):
            this_tile_size_viable = False
            for x_offset in range(square_size):
                for y_offset in range(square_size):
                    this_offset_viable = True
                    for xx in range(square_size):
                        for yy in range(square_size):
                            if (
                                x + xx - x_offset,
                                y + yy - y_offset,
                            ) not in s.visited_tiles:
                                this_offset_viable = False
                                break
                        if not this_offset_viable:
                            break
                    if this_offset_viable:
                        s.max_square_size = square_size
                        s.square_x = x - x_offset
                        s.square_y = y - y_offset
                        rows.append(
                            {
                                "time": row["time"],
                                "max_square_size": square_size,
                                "square_x": s.square_x,
                                "square_y": s.square_y,
                            }
                        )
                        this_tile_size_viable = True
                        break
                if this_tile_size_viable:
                    break
            if not this_tile_size_viable:
                break

    new_square_history = pd.DataFrame(rows)
    s.square_evolution = pd.concat([s.square_evolution, new_square_history])
    s.square_start = len(tiles)
