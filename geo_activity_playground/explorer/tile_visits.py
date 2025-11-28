import collections
import datetime
import itertools
import logging
import pathlib
import pickle
import zoneinfo
from typing import Iterator
from typing import Optional
from typing import TypedDict

import pandas as pd
from tqdm import tqdm

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.datamodel import Activity
from ..core.datamodel import DB
from ..core.datamodel import TileFirstVisit
from ..core.paths import atomic_open
from ..core.tasks import try_load_pickle
from ..core.tasks import work_tracker_path
from ..core.tasks import WorkTracker
from ..core.tiles import adjacent_to
from ..core.tiles import interpolate_missing_tile

logger = logging.getLogger(__name__)


def get_first_visits_for_activity(
    activity_id: int, zoom: Optional[int] = None
) -> list[TileFirstVisit]:
    """Get all tiles that were first visited by the given activity.

    Args:
        activity_id: The activity ID to query for.
        zoom: Optional zoom level to filter by. If None, returns all zoom levels.

    Returns:
        List of TileFirstVisit records.
    """
    query = DB.session.query(TileFirstVisit).filter(
        TileFirstVisit.activity_id == activity_id
    )
    if zoom is not None:
        query = query.filter(TileFirstVisit.zoom == zoom)
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
        DB.session.query(TileFirstVisit)
        .filter(TileFirstVisit.zoom == zoom)
        .order_by(TileFirstVisit.time)
        .all()
    )

    if not visits:
        return pd.DataFrame(columns=["activity_id", "time", "tile_x", "tile_y"])

    return pd.DataFrame(
        {
            "activity_id": [v.activity_id for v in visits],
            "time": [pd.Timestamp(v.time) if v.time else pd.NaT for v in visits],
            "tile_x": [v.tile_x for v in visits],
            "tile_y": [v.tile_y for v in visits],
        }
    )


def get_tile_count(zoom: int) -> int:
    """Get the count of explored tiles at a zoom level."""
    return DB.session.query(TileFirstVisit).filter(TileFirstVisit.zoom == zoom).count()


def get_tile_medians(zoom: int) -> tuple[int, int]:
    """Get the median tile_x and tile_y for centering the map.

    Returns:
        Tuple of (median_tile_x, median_tile_y)
    """
    from sqlalchemy import func

    result = DB.session.query(
        func.avg(TileFirstVisit.tile_x), func.avg(TileFirstVisit.tile_y)
    ).filter(TileFirstVisit.zoom == zoom).first()

    if result and result[0] is not None:
        return (int(result[0]), int(result[1]))
    return (0, 0)


class TileInfo(TypedDict):
    activity_ids: set[int]
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
        self.square_x: Optional[int] = None
        self.square_y: Optional[int] = None


class TileState(TypedDict):
    tile_visits: dict[int, dict[tuple[int, int], TileInfo]]
    activities_per_tile: dict[int, dict[tuple[int, int], set[int]]]
    evolution_state: dict[int, TileEvolutionState]
    version: int


# Version 3: Removed tile_history (now stored in database)
TILE_STATE_VERSION = 3


class TileVisitAccessor:
    PATH = pathlib.Path("Cache/tile-state-3.pickle")
    OLD_PATH = pathlib.Path("Cache/tile-state-2.pickle")

    def __init__(self) -> None:
        self.tile_state: TileState = try_load_pickle(self.PATH)
        self._pending_migration: Optional[dict] = None

        if self.tile_state is None:
            # Try loading old pickle - defer DB migration until we have app context
            old_state = try_load_pickle(self.OLD_PATH)
            if old_state is not None:
                logger.info("Found old tile-state-2.pickle, will migrate to v3...")
                # Copy over the non-DB fields now
                self.tile_state = make_tile_state()
                if "tile_visits" in old_state:
                    self.tile_state["tile_visits"] = old_state["tile_visits"]
                if "activities_per_tile" in old_state:
                    self.tile_state["activities_per_tile"] = old_state["activities_per_tile"]
                if "evolution_state" in old_state:
                    self.tile_state["evolution_state"] = old_state["evolution_state"]
                # Store old state for DB migration later (needs app context)
                self._pending_migration = old_state
                self.save()
            else:
                self.tile_state = make_tile_state()
        elif self.tile_state.get("version", None) != TILE_STATE_VERSION:
            self.tile_state = make_tile_state()

    def complete_migration(self) -> None:
        """Complete pending migration to database. Must be called with app context."""
        if self._pending_migration is not None:
            logger.info("Completing tile_history migration to database...")
            _migrate_tile_history_to_db(self._pending_migration)
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
        "tile_visits": collections.defaultdict(make_defaultdict_dict),
        "activities_per_tile": collections.defaultdict(make_defaultdict_set),
        "evolution_state": collections.defaultdict(TileEvolutionState),
        "version": TILE_STATE_VERSION,
    }
    return tile_state


def _consistency_check(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> bool:
    present_activity_ids = set(repository.get_activity_ids())

    for zoom, activities_per_tile in tile_visit_accessor.tile_state[
        "activities_per_tile"
    ].items():
        for tile, tile_activity_ids in activities_per_tile.items():
            deleted_activity_ids = tile_activity_ids - present_activity_ids
            if deleted_activity_ids:
                logger.info(f"Activities {deleted_activity_ids} have been deleted.")
                return False

    for zoom, tile_visits in tile_visit_accessor.tile_state["tile_visits"].items():
        for tile, meta in tile_visits.items():
            if not pd.isna(meta["first_time"]) and meta["first_time"].tzinfo is None:
                logger.info("Tile visits are stored without time zone.")
                return False
            if meta["first_id"] not in present_activity_ids:
                logger.info(f"Activity {meta['first_id']} have been deleted.")
                return False
            if meta["last_id"] not in present_activity_ids:
                logger.info(f"Activity {meta['last_id']} have been deleted.")
                return False

    return True


def _reset_tile_first_visits_db() -> None:
    """Clear all TileFirstVisit records from the database."""
    DB.session.query(TileFirstVisit).delete()
    DB.session.commit()
    logger.info("Cleared tile_first_visits table in database.")


def _migrate_tile_history_to_db(old_tile_state: dict) -> None:
    """Migrate existing tile_history data to the TileFirstVisit database table.

    This is a one-time migration for users upgrading from pickle-only storage
    (version 2 or earlier). It checks if the DB is empty and the pickle has
    tile_history data, then migrates.
    """
    # Check if DB already has data
    existing_count = DB.session.query(TileFirstVisit).limit(1).count()
    if existing_count > 0:
        return  # Already migrated

    # Check if old pickle has tile_history to migrate
    tile_history = old_tile_state.get("tile_history", {})
    if not tile_history:
        return  # Nothing to migrate

    total_records = sum(
        len(df) for df in tile_history.values() if isinstance(df, pd.DataFrame)
    )
    if total_records == 0:
        return  # Nothing to migrate

    logger.info(f"Migrating {total_records} tile first visits from pickle to database...")

    for zoom, tile_history_df in tile_history.items():
        if not isinstance(tile_history_df, pd.DataFrame) or tile_history_df.empty:
            continue

        batch: list[TileFirstVisit] = []
        for _, row in tile_history_df.iterrows():
            time = row["time"]
            db_time = time.to_pydatetime() if pd.notna(time) else None
            batch.append(
                TileFirstVisit(
                    zoom=zoom,
                    tile_x=int(row["tile_x"]),
                    tile_y=int(row["tile_y"]),
                    activity_id=int(row["activity_id"]),
                    time=db_time,
                )
            )

            # Commit in batches to avoid memory issues
            if len(batch) >= 1000:
                DB.session.add_all(batch)
                DB.session.commit()
                batch = []

        if batch:
            DB.session.add_all(batch)
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
        _reset_tile_first_visits_db()
        work_tracker.reset()

    for activity_id in tqdm(
        work_tracker.filter(repository.get_activity_ids()), desc="Tile visits", delay=1
    ):
        _process_activity(repository, tile_visit_accessor.tile_state, activity_id)
        work_tracker.mark_done(activity_id)

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
        new_tile_first_visits: list[TileFirstVisit] = []

        activity_tiles = activity_tiles.groupby(["tile_x", "tile_y"]).head(1)

        for time, tile in zip(
            activity_tiles["time"],
            zip(activity_tiles["tile_x"], activity_tiles["tile_y"]),
        ):
            if activity.kind.consider_for_achievements:
                if time is not None and time.tz is None:
                    time = time.tz_localize("UTC")
                if tile not in tile_state["tile_visits"][zoom]:
                    # Record new tile in database
                    db_time = time.to_pydatetime() if pd.notna(time) else None
                    new_tile_first_visits.append(
                        TileFirstVisit(
                            zoom=zoom,
                            tile_x=tile[0],
                            tile_y=tile[1],
                            activity_id=activity_id,
                            time=db_time,
                        )
                    )

                tile_visit = tile_state["tile_visits"][zoom][tile]
                if not tile_visit:
                    tile_visit["activity_ids"] = {activity_id}
                else:
                    tile_visit["activity_ids"].add(activity_id)

                first_time = tile_visit.get("first_time", None)
                last_time = tile_visit.get("last_time", None)
                if first_time is not None and first_time.tz is None:
                    first_time = first_time.tz_localize("UTC")
                if last_time is not None and last_time.tz is None:
                    last_time = last_time.tz_localize("UTC")
                try:
                    if first_time is None or time < first_time:
                        tile_visit["first_id"] = activity_id
                        tile_visit["first_time"] = time
                    if last_time is None or time > last_time:
                        tile_visit["last_id"] = activity_id
                        tile_visit["last_time"] = time
                except TypeError as e:
                    raise TypeError(
                        f"Mismatch in timezone awareness: {time=}, {first_time=}, {last_time=}"
                    ) from e

            activities_per_tile[tile].add(activity_id)

        # Write new first visits to database
        if new_tile_first_visits:
            DB.session.add_all(new_tile_first_visits)
            DB.session.commit()

        # Move up one layer in the quad-tree.
        activity_tiles["tile_x"] //= 2
        activity_tiles["tile_y"] //= 2


def _tiles_from_points(
    time_series: pd.DataFrame, zoom: int
) -> Iterator[tuple[datetime.datetime, int, int]]:
    # XXX Some people haven't localized their time series yet. This breaks the tile history part. Just assume that it is UTC, should be good enough for tiles.
    if time_series["time"].dt.tz is None:
        time_series = time_series.copy()
        time_series["time"].dt.tz_localize(zoneinfo.ZoneInfo("UTC"))
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


def _compute_cluster_evolution(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    if len(s.cluster_evolution) > 0:
        max_cluster_so_far = s.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_so_far = 0

    rows = []
    for index, row in tqdm(
        tiles.iloc[s.cluster_start :].iterrows(),
        desc=f"Cluster evolution for {zoom=}",
        delay=1,
    ):
        new_clusters = False
        # Current tile.
        tile = (row["tile_x"], row["tile_y"])

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
                max_cluster_size = max_cluster_so_far

    new_cluster_evolution = pd.DataFrame(rows)
    s.cluster_evolution = pd.concat([s.cluster_evolution, new_cluster_evolution])
    s.cluster_start = len(tiles)


def _compute_square_history(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    rows = []
    for index, row in tqdm(
        tiles.iloc[s.square_start :].iterrows(),
        desc=f"Square evolution for {zoom=}",
        delay=1,
    ):
        tile = (row["tile_x"], row["tile_y"])
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
