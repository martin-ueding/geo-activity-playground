import json
import pathlib
from typing import Iterator

import altair as alt
import geojson
import pandas as pd

from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon


def adjacent_to(tile: tuple[int, int]) -> Iterator[tuple[int, int]]:
    x, y = tile
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)


class ExplorerClusterState:
    def __init__(self, zoom: int) -> None:
        self.num_neighbors: dict[tuple[int, int], int] = {}
        self.cluster_tiles: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.cluster_evolution = pd.DataFrame()
        self.start = 0

        self._state_path = pathlib.Path(f"Cache/explorer_cluster_{zoom}_state.json")
        self._cluster_evolution_path = pathlib.Path(
            f"Cache/explorer_cluster_{zoom}_evolution.parquet"
        )

    def load(self) -> None:
        if self._state_path.exists():
            with open(self._state_path) as f:
                data = json.load(f)
            self.num_neighbors = {
                tuple(map(int, key.split("/"))): value
                for key, value in data["num_neighbors"].items()
            }
            self.cluster_tiles = {
                tuple(map(int, key.split("/"))): [
                    tuple(t) for t in data["clusters"][str(value)]
                ]
                for key, value in data["memberships"].items()
            }
            self.start = data["start"]

        if self._cluster_evolution_path.exists():
            self.cluster_evolution = pd.read_parquet(self._cluster_evolution_path)

    def save(self) -> None:
        data = {
            "num_neighbors": {
                f"{x}/{y}": count for (x, y), count in self.num_neighbors.items()
            },
            "memberships": {
                f"{x}/{y}": id(members)
                for (x, y), members in self.cluster_tiles.items()
            },
            "clusters": {
                id(members): members for members in self.cluster_tiles.values()
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
            s.cluster_tiles[tile] = [tile]

        # Also make the adjacent tiles their own clusters, if they are full.
        this_and_neighbors = [tile] + list(adjacent_to(tile))
        for other in this_and_neighbors:
            if s.num_neighbors.get(other, 0) == 4:
                s.cluster_tiles[other] = [other]

        for candidate in this_and_neighbors:
            if candidate not in s.cluster_tiles:
                continue
            # The candidate is a cluster tile. Let's see whether any of the neighbors are also cluster tiles but with a different cluster. Then we need to join them.
            for other in adjacent_to(candidate):
                if other not in s.cluster_tiles:
                    continue
                # The other tile is also a cluster tile.
                if s.cluster_tiles[candidate] is s.cluster_tiles[other]:
                    continue
                # The two clusters are not the same. We add the other's cluster tile to this tile.
                s.cluster_tiles[candidate].extend(s.cluster_tiles[other])
                # Update the other cluster tiles that they now point to the new cluster. This also updates the other tile.
                for member in s.cluster_tiles[other]:
                    s.cluster_tiles[member] = s.cluster_tiles[candidate]
                new_clusters = True

        if new_clusters:
            max_cluster_size = max(
                (len(members) for members in s.cluster_tiles.values()),
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
