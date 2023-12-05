import itertools
import json
import logging
import pathlib
from typing import Iterator

import geojson
import pandas as pd

from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon


logger = logging.getLogger(__name__)


def adjacent_to(tile: tuple[int, int]) -> Iterator[tuple[int, int]]:
    x, y = tile
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)


class ExplorerClusterState:
    def __init__(self, zoom: int) -> None:
        self.num_neighbors: dict[tuple[int, int], int] = {}
        self.memberships: dict[tuple[int, int], tuple[int, int]] = {}
        self.clusters: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.cluster_evolution = pd.DataFrame()
        self.start = 0

        self._state_path = pathlib.Path(f"Cache/explorer_cluster_{zoom}_state_v2.json")
        self._cluster_evolution_path = pathlib.Path(
            f"Cache/explorer_cluster_{zoom}_evolution.parquet"
        )

    def load(self) -> None:
        logger.info("Loading explorer cluster state …")
        if self._state_path.exists():
            with open(self._state_path) as f:
                data = json.load(f)
            self.num_neighbors = {
                tuple(map(int, key.split("/"))): value
                for key, value in data["num_neighbors"].items()
            }
            self.memberships = {
                tuple(map(int, key.split("/"))): tuple(value)
                for key, value in data["memberships"].items()
            }
            self.clusters = {
                tuple(map(int, key.split("/"))): [tuple(t) for t in value]
                for key, value in data["clusters"].items()
            }
            self.start = data["start"]

        if self._cluster_evolution_path.exists():
            self.cluster_evolution = pd.read_parquet(self._cluster_evolution_path)

    def save(self) -> None:
        logger.info("Saving explorer cluster state …")
        data = {
            "num_neighbors": {
                f"{x}/{y}": count for (x, y), count in self.num_neighbors.items()
            },
            "memberships": {
                f"{x}/{y}": value for (x, y), value in self.memberships.items()
            },
            "clusters": {
                f"{x}/{y}": [tuple(member) for member in members]
                for (x, y), members in self.clusters.items()
            },
            "start": self.start,
        }
        with open(self._state_path, "w") as f:
            json.dump(data, f)

        self.cluster_evolution.to_parquet(self._cluster_evolution_path)


def get_explorer_cluster_evolution(zoom: int) -> ExplorerClusterState:
    tiles = pd.read_parquet(pathlib.Path(f"Cache/first_time_per_tile_{zoom}.parquet"))
    tiles.sort_values("first_time", inplace=True)

    s = ExplorerClusterState(zoom)
    s.load()

    logger.info("Compute new explorer cluster state …")

    if len(s.cluster_evolution) > 0:
        max_cluster_so_far = s.cluster_evolution["max_cluster_size"].iloc[-1]
    else:
        max_cluster_so_far = 0

    rows = []
    for index, row in tiles.iloc[s.start :].iterrows():
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
                        "time": row["first_time"],
                        "max_cluster_size": max_cluster_size,
                    }
                )
                max_cluster_size = max_cluster_so_far

    new_cluster_evolution = pd.DataFrame(rows)
    s.cluster_evolution = pd.concat([s.cluster_evolution, new_cluster_evolution])
    s.start = len(tiles)
    s.save()
    return s


def bounding_box_for_biggest_cluster(
    clusters: list[list[tuple[int, int]]], zoom: int
) -> str:
    biggest_cluster = max(clusters, key=lambda members: len(members))
    min_x = min(x for x, y in biggest_cluster)
    max_x = max(x for x, y in biggest_cluster)
    min_y = min(y for x, y in biggest_cluster)
    max_y = max(y for x, y in biggest_cluster)
    lat_max, lon_min = get_tile_upper_left_lat_lon(min_x, min_y, zoom)
    lat_min, lon_max = get_tile_upper_left_lat_lon(max_x, max_y, zoom)
    return geojson.dumps(
        geojson.Feature(
            geometry=geojson.Polygon(
                [
                    [
                        (lon_min, lat_max),
                        (lon_max, lat_max),
                        (lon_max, lat_min),
                        (lon_min, lat_min),
                        (lon_min, lat_max),
                    ]
                ]
            ),
        )
    )


class SquareHistoryState:
    def __init__(self, zoom: int) -> None:
        self._state_path = pathlib.Path(f"Cache/square_history_{zoom}_state.json")
        self._square_history_path = pathlib.Path(f"Cache/square_history_{zoom}.parquet")

        self.max_square_size = 0
        self.start = 0
        self.visited_tiles = set()
        self.square_history = pd.DataFrame()

    def load(self) -> None:
        logger.info("Load explorer square state …")
        if self._state_path.exists():
            with open(self._state_path) as f:
                data = json.load(f)
            self.visited_tiles = set((x, y) for x, y in data["visited_tiles"])
            self.max_square_size = data["max_square_size"]
            self.start = data["start"]

        if self._square_history_path.exists():
            self.square_history = pd.read_parquet(self._square_history_path)

    def save(self) -> None:
        logger.info("Save explorer square state …")
        data = {
            "max_square_size": self.max_square_size,
            "visited_tiles": list(self.visited_tiles),
            "start": self.start,
        }
        with open(self._state_path, "w") as f:
            json.dump(data, f)

        self.square_history.to_parquet(self._square_history_path)


def get_square_history(zoom: int) -> SquareHistoryState:
    tiles = pd.read_parquet(f"Cache/first_time_per_tile_{zoom}.parquet")
    tiles.sort_values("first_time", inplace=True)
    s = SquareHistoryState(zoom)
    s.load()
    logger.info("Compute new explorer square state …")
    rows = []
    for index, row in tiles.iloc[s.start :].iterrows():
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
                        rows.append(
                            {"time": row["first_time"], "max_square_size": square_size}
                        )
                        this_tile_size_viable = True
                        break
                if this_tile_size_viable:
                    break
            if not this_tile_size_viable:
                break

    new_square_history = pd.DataFrame(rows)
    s.square_history = pd.concat([s.square_history, new_square_history])
    s.start = len(tiles)
    s.save()
    return s
