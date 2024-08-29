import collections
import datetime
import itertools
import logging
import pathlib
import pickle
from typing import Any
from typing import Optional
from typing import TypedDict

import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.paths import tiles_per_time_series
from geo_activity_playground.core.tasks import try_load_pickle
from geo_activity_playground.core.tasks import work_tracker_path
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.core.tiles import adjacent_to
from geo_activity_playground.core.tiles import tiles_from_points


logger = logging.getLogger(__name__)


class TileHistoryRow(TypedDict):
    time: datetime.datetime
    tile_x: int
    tile_y: int


class TileVisitAccessor:
    TILE_EVOLUTION_STATES_PATH = pathlib.Path("Cache/tile-evolution-state.pickle")
    TILE_HISTORIES_PATH = pathlib.Path(f"Cache/tile-history.pickle")
    TILE_VISITS_PATH = pathlib.Path(f"Cache/tile-visits.pickle")
    ACTIVITIES_PER_TILE_PATH = pathlib.Path(f"Cache/activities-per-tile.pickle")

    def __init__(self) -> None:
        self.visits: dict[int, dict[tuple[int, int], dict[str, Any]]] = try_load_pickle(
            self.TILE_VISITS_PATH
        ) or collections.defaultdict(dict)
        "zoom → (tile_x, tile_y) → tile_info"

        self.histories: dict[int, pd.DataFrame] = try_load_pickle(
            self.TILE_HISTORIES_PATH
        ) or collections.defaultdict(pd.DataFrame)

        self.states = try_load_pickle(
            self.TILE_EVOLUTION_STATES_PATH
        ) or collections.defaultdict(TileEvolutionState)

        self.activities_per_tile: dict[
            int, dict[tuple[int, int], set[int]]
        ] = try_load_pickle(self.ACTIVITIES_PER_TILE_PATH) or collections.defaultdict(
            dict
        )

    def save(self) -> None:
        with open(self.TILE_VISITS_PATH, "wb") as f:
            pickle.dump(self.visits, f)

        with open(self.TILE_HISTORIES_PATH, "wb") as f:
            pickle.dump(self.histories, f)

        with open(self.TILE_EVOLUTION_STATES_PATH, "wb") as f:
            pickle.dump(self.states, f)

        with open(self.ACTIVITIES_PER_TILE_PATH, "wb") as f:
            pickle.dump(self.activities_per_tile, f)


def compute_tile_visits(
    repository: ActivityRepository, tile_visits_accessor: TileVisitAccessor
) -> None:
    present_activity_ids = repository.get_activity_ids()
    work_tracker = WorkTracker(work_tracker_path("tile-visits"))

    changed_zoom_tile = collections.defaultdict(set)

    # Delete visits from removed activities.
    for zoom, activities_per_tile in tile_visits_accessor.activities_per_tile.items():
        for tile, activity_ids in activities_per_tile.items():
            deleted_ids = activity_ids - present_activity_ids
            if deleted_ids:
                logger.debug(
                    f"Removing activities {deleted_ids} from tile {tile} at {zoom=}."
                )
                for activity_id in deleted_ids:
                    activity_ids.remove(activity_id)
                    work_tracker.discard(activity_id)
                    changed_zoom_tile[zoom].add(tile)

    # Add visits from new activities.
    activity_ids_to_process = work_tracker.filter(repository.get_activity_ids())
    for activity_id in tqdm(
        activity_ids_to_process, desc="Extract explorer tile visits"
    ):
        for zoom in range(20):
            for time, tile_x, tile_y in tiles_from_points(
                repository.get_time_series(activity_id), zoom
            ):
                tile = (tile_x, tile_y)
                if tile not in tile_visits_accessor.activities_per_tile[zoom]:
                    tile_visits_accessor.activities_per_tile[zoom][tile] = set()
                tile_visits_accessor.activities_per_tile[zoom][tile].add(activity_id)
                changed_zoom_tile[zoom].add(tile)
        work_tracker.mark_done(activity_id)

    # Update tile visits structure.
    for zoom, changed_tiles in tqdm(
        changed_zoom_tile.items(), desc="Incorporate changes in tiles"
    ):
        soa = {"activity_id": [], "time": [], "tile_x": [], "tile_y": []}

        for tile in changed_tiles:
            activity_ids = tile_visits_accessor.activities_per_tile[zoom][tile]
            activities = [
                repository.get_activity_by_id(activity_id)
                for activity_id in activity_ids
            ]
            activities_to_consider = [
                activity
                for activity in activities
                if activity["consider_for_achievements"]
            ]
            activities_to_consider.sort(key=lambda activity: activity["start"])

            if activities_to_consider:
                tile_visits_accessor.visits[zoom][tile] = {
                    "first_time": activities_to_consider[0]["start"],
                    "first_id": activities_to_consider[0]["id"],
                    "last_time": activities_to_consider[-1]["start"],
                    "last_id": activities_to_consider[-1]["id"],
                    "activity_ids": {
                        activity["id"] for activity in activities_to_consider
                    },
                }

                soa["activity_id"].append(activities_to_consider[0]["id"])
                soa["time"].append(activities_to_consider[0]["start"])
                soa["tile_x"].append(tile[0])
                soa["tile_y"].append(tile[1])
            else:
                if tile in tile_visits_accessor.visits[zoom]:
                    del tile_visits_accessor.visits[zoom][tile]

        df = pd.DataFrame(soa)
        if len(df) > 0:
            df = pd.concat([tile_visits_accessor.histories[zoom], df])
            df.sort_values("time", inplace=True)
            tile_visits_accessor.histories[zoom] = df.groupby(
                ["tile_x", "tile_y"]
            ).head(1)

    tile_visits_accessor.save()
    work_tracker.close()


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


def compute_tile_evolution(
    tile_visits_accessor: TileVisitAccessor, config: Config
) -> None:
    for zoom in config.explorer_zoom_levels:
        _compute_cluster_evolution(
            tile_visits_accessor.histories[zoom],
            tile_visits_accessor.states[zoom],
            zoom,
        )
        _compute_square_history(
            tile_visits_accessor.histories[zoom],
            tile_visits_accessor.states[zoom],
            zoom,
        )

    tile_visits_accessor.save()


def _compute_cluster_evolution(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    if len(s.cluster_evolution) > 0:
        max_cluster_so_far = s.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_so_far = 0

    rows = []
    for index, row in tqdm(
        tiles.iloc[s.cluster_start :].iterrows(), desc=f"Cluster evolution for {zoom=}"
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
        tiles.iloc[s.square_start :].iterrows(), desc=f"Square evolution for {zoom=}"
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
