import collections
import datetime
import itertools
import logging
import pathlib
import pickle
from typing import Any
from typing import Iterator

import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.tasks import try_load_pickle
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.core.tiles import adjacent_to
from geo_activity_playground.core.tiles import interpolate_missing_tile


logger = logging.getLogger(__name__)

TILE_EVOLUTION_STATES_PATH = pathlib.Path("Cache/tile-evolution-state.pickle")
TILE_HISTORIES_PATH = pathlib.Path(f"Cache/tile-history.pickle")
TILE_VISITS_PATH = pathlib.Path(f"Cache/tile-visits.pickle")


def compute_tile_visits(repository: ActivityRepository) -> None:
    tile_visits: dict[int, dict[tuple[int, int], dict[str, Any]]] = try_load_pickle(
        TILE_VISITS_PATH
    ) or collections.defaultdict(dict)
    tile_history: dict[int, pd.DataFrame] = try_load_pickle(
        TILE_HISTORIES_PATH
    ) or collections.defaultdict(pd.DataFrame)

    work_tracker = WorkTracker("tile-visits")
    activity_ids_to_process = work_tracker.filter(repository.activity_ids)
    new_tile_history_rows = collections.defaultdict(list)
    for activity_id in tqdm(
        activity_ids_to_process, desc="Extract explorer tile visits"
    ):
        time_series = repository.get_time_series(activity_id)
        for zoom in range(20):
            for time, tile_x, tile_y in _tiles_from_points(time_series, zoom):
                tile = (tile_x, tile_y)
                if tile in tile_visits[zoom]:
                    d = tile_visits[zoom][tile]
                    d["count"] += 1
                    if d["first_time"] > time:
                        d["first_time"] = time
                        d["first_id"] = activity_id
                    if d["last_time"] < time:
                        d["last_time"] = time
                        d["last_id"] = activity_id
                    d["activity_ids"].add(activity_id)
                else:
                    tile_visits[zoom][tile] = {
                        "count": 1,
                        "first_time": time,
                        "first_id": activity_id,
                        "last_time": time,
                        "last_id": activity_id,
                        "activity_ids": {activity_id},
                    }
                    new_tile_history_rows[zoom].append(
                        {
                            "activity_id": activity_id,
                            "time": time,
                            "tile_x": tile_x,
                            "tile_y": tile_y,
                        }
                    )
        work_tracker.mark_done(activity_id)

    if activity_ids_to_process:
        with open(TILE_VISITS_PATH, "wb") as f:
            pickle.dump(tile_visits, f)

        for zoom, new_rows in new_tile_history_rows.items():
            new_df = pd.DataFrame(new_rows)
            new_df.sort_values("time", inplace=True)
            tile_history[zoom] = pd.concat([tile_history[zoom], new_df])

        with open(TILE_HISTORIES_PATH, "wb") as f:
            pickle.dump(tile_history, f)

    work_tracker.close()


def _tiles_from_points(
    time_series: pd.DataFrame, zoom: int
) -> Iterator[tuple[datetime.datetime, int, int]]:
    assert pd.api.types.is_dtype_equal(time_series["time"].dtype, "datetime64[ns, UTC]")
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


class TileEvolutionState:
    def __init__(self) -> None:
        self.num_neighbors: dict[tuple[int, int], int] = {}
        self.memberships: dict[tuple[int, int], tuple[int, int]] = {}
        self.clusters: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.cluster_evolution = pd.DataFrame()
        self.square_start = 0
        self.cluster_start = 0
        self.max_square_size = 0
        self.visited_tiles = set()
        self.square_evolution = pd.DataFrame()
        self.square_x = None
        self.square_y = None


def compute_tile_evolution() -> None:
    with open(TILE_HISTORIES_PATH, "rb") as f:
        tile_histories = pickle.load(f)

    states = try_load_pickle(TILE_EVOLUTION_STATES_PATH) or collections.defaultdict(
        TileEvolutionState
    )

    zoom_levels = list(reversed(list(range(20))))

    for zoom in tqdm(zoom_levels, desc="Compute explorer cluster evolution"):
        _compute_cluster_evolution(tile_histories[zoom], states[zoom])
    for zoom in tqdm(zoom_levels, desc="Compute explorer square evolution"):
        _compute_square_history(tile_histories[zoom], states[zoom])

    with open(TILE_EVOLUTION_STATES_PATH, "wb") as f:
        pickle.dump(states, f)


def _compute_cluster_evolution(tiles: pd.DataFrame, s: TileEvolutionState) -> None:
    if len(s.cluster_evolution) > 0:
        max_cluster_so_far = s.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_so_far = 0

    rows = []
    for index, row in tiles.iloc[s.cluster_start :].iterrows():
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


def _compute_square_history(tiles: pd.DataFrame, s: TileEvolutionState) -> None:
    rows = []
    for index, row in tiles.iloc[s.square_start :].iterrows():
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
