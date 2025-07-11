import collections
import datetime
import itertools
import logging
import pathlib
import pickle
from typing import Iterator
from typing import Optional
from typing import TypedDict

import pandas as pd
from tqdm import tqdm

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.datamodel import Activity
from ..core.datamodel import DB
from ..core.paths import atomic_open
from ..core.tasks import try_load_pickle
from ..core.tasks import work_tracker_path
from ..core.tasks import WorkTracker
from ..core.tiles import adjacent_to
from ..core.tiles import interpolate_missing_tile

# import sqlalchemy as sa

# from sqlalchemy import Column
# from sqlalchemy import ForeignKey
# from sqlalchemy import String
# from sqlalchemy import Table
# from sqlalchemy.orm import DeclarativeBase
# from sqlalchemy.orm import Mapped
# from sqlalchemy.orm import mapped_column
# from sqlalchemy.orm import relationship

logger = logging.getLogger(__name__)


# class VisitedTile(DB.Model):
#     __tablename__ = "visited_tiles"

#     zoom: Mapped[int] = mapped_column(primary_key=True)
#     x: Mapped[int] = mapped_column(primary_key=True)
#     y: Mapped[int] = mapped_column(primary_key=True)

#     first_activity_id: Mapped[int] = mapped_column(
#         ForeignKey("Activity.id", name="first_activity_id"), nullable=True
#     )
#     first_activity: Mapped[Activity] = relationship(back_populates="activities")
#     first_visit: Mapped[Optional[datetime.datetime]] = mapped_column(
#         sa.DateTime, nullable=True
#     )

#     __table_args__ =  (
#         sa.PrimaryKeyConstraint(zoom, x, y),
#         {},
#     )


class TileInfo(TypedDict):
    activity_ids: set[int]
    first_time: datetime.datetime
    first_id: int
    last_time: datetime.datetime
    last_id: int


class TileHistoryRow(TypedDict):
    activity_id: int
    time: datetime.datetime
    tile_x: int
    tile_y: int


class TileEvolutionState:
    def __init__(self) -> None:
        self.num_neighbors: dict[tuple[int, int], int] = {}
        self.memberships: dict[tuple[int, int], tuple[int, int]] = {}
        self.clusters: dict[tuple[int, int], list[tuple[int, int]]] = {}
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
    tile_history: dict[int, pd.DataFrame]
    activities_per_tile: dict[int, dict[tuple[int, int], set[int]]]
    evolution_state: dict[int, TileEvolutionState]
    version: int


TILE_STATE_VERSION = 2


class TileVisitAccessor:
    PATH = pathlib.Path("Cache/tile-state-2.pickle")

    def __init__(self) -> None:
        self.tile_state: TileState = try_load_pickle(self.PATH)
        if (
            self.tile_state is None
            or self.tile_state.get("version", None) != TILE_STATE_VERSION
        ):
            self.tile_state = make_tile_state()
            # TODO: Reset work tracker

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
        "tile_history": collections.defaultdict(pd.DataFrame),
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


def compute_tile_visits_new(
    repository: ActivityRepository, tile_visit_accessor: TileVisitAccessor
) -> None:
    work_tracker = WorkTracker(work_tracker_path("tile-state"))

    if not _consistency_check(repository, tile_visit_accessor):
        logger.warning("Need to recompute Explorer Tiles due to deleted activities.")
        tile_visit_accessor.reset()
        work_tracker.reset()

    for activity_id in tqdm(
        work_tracker.filter(repository.get_activity_ids()), desc="Tile visits", delay=1
    ):
        _process_activity(repository, tile_visit_accessor.tile_state, activity_id)
        work_tracker.mark_done(activity_id)

    for zoom in reversed(range(20)):
        tile_state = tile_visit_accessor.tile_state
        if not (
            tile_state["tile_history"][zoom]["time"].diff().dropna()
            >= datetime.timedelta(seconds=0)
        ).all():
            logger.warning(
                f"The order of the tile history at {zoom=} is not chronological, resetting."
            )
            new_tile_history_soa: dict[str, list] = {
                "activity_id": [],
                "time": [],
                "tile_x": [],
                "tile_y": [],
            }
            for tile, visit in tile_state["tile_visits"][zoom].items():
                new_tile_history_soa["activity_id"].append(visit["first_id"])
                new_tile_history_soa["time"].append(visit["first_time"])
                new_tile_history_soa["tile_x"].append(tile[0])
                new_tile_history_soa["tile_y"].append(tile[1])
            tile_state["tile_history"][zoom] = pd.DataFrame(new_tile_history_soa)
            tile_state["tile_history"][zoom].sort_values("time", inplace=True)
            # Reset the evolution state.
            tile_state["evolution_state"] = collections.defaultdict(TileEvolutionState)
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

        new_tile_history_soa: dict[str, list] = {
            "activity_id": [],
            "time": [],
            "tile_x": [],
            "tile_y": [],
        }

        activity_tiles = activity_tiles.groupby(["tile_x", "tile_y"]).head(1)

        for time, tile in zip(
            activity_tiles["time"],
            zip(activity_tiles["tile_x"], activity_tiles["tile_y"]),
        ):
            if activity.kind.consider_for_achievements:
                if tile not in tile_state["tile_visits"][zoom]:
                    new_tile_history_soa["activity_id"].append(activity_id)
                    new_tile_history_soa["time"].append(time)
                    new_tile_history_soa["tile_x"].append(tile[0])
                    new_tile_history_soa["tile_y"].append(tile[1])

                tile_visit = tile_state["tile_visits"][zoom][tile]
                if not tile_visit:
                    tile_visit["activity_ids"] = {activity_id}
                else:
                    tile_visit["activity_ids"].add(activity_id)

                first_time = tile_visit.get("first_time", None)
                last_time = tile_visit.get("last_time", None)
                if first_time is None or time < first_time:
                    tile_visit["first_id"] = activity_id
                    tile_visit["first_time"] = time
                if last_time is None or time > last_time:
                    tile_visit["last_id"] = activity_id
                    tile_visit["last_time"] = time

            activities_per_tile[tile].add(activity_id)

        if new_tile_history_soa["activity_id"]:
            tile_state["tile_history"][zoom] = pd.concat(
                [tile_state["tile_history"][zoom], pd.DataFrame(new_tile_history_soa)]
            )

        # Move up one layer in the quad-tree.
        activity_tiles["tile_x"] //= 2
        activity_tiles["tile_y"] //= 2


def _tiles_from_points(
    time_series: pd.DataFrame, zoom: int
) -> Iterator[tuple[datetime.datetime, int, int]]:
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
        _compute_cluster_evolution(
            tile_state["tile_history"][zoom],
            tile_state["evolution_state"][zoom],
            zoom,
        )
        _compute_square_history(
            tile_state["tile_history"][zoom],
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
