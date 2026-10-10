"""Proposals for new places from recurring stays that don't match a place.

The stays are first binned into cells of about 10 m, such that the number of
neighbor pairs doesn't grow quadratically with the number of stays at a
frequently visited location. The cells are then grouped with the greedy center
clustering from the similar routes. A group is proposed if its stays come from
enough distinct activities.
"""

import dataclasses
import math

import numpy as np
import pandas as pd
import shapely
import sqlalchemy

from ...core.coordinates import get_distance
from ...core.datamodel import DB
from ...core.tiles import compute_tile_float
from ..similar_routes.clustering import Neighbors, cluster_routes
from .model import PLACE_RADIUS_M, Stay

MIN_ACTIVITIES = 3
CELL_ZOOM = 22
METERS_PER_DEGREE = 6371e3 * math.pi / 180


@dataclasses.dataclass
class ProposedPlace:
    latitude: float
    longitude: float
    num_stays: int
    num_activities: int


def propose_places() -> list[ProposedPlace]:
    stays = pd.DataFrame(
        DB.session.execute(
            sqlalchemy.select(Stay.activity_id, Stay.latitude, Stay.longitude).where(
                Stay.place_id.is_(None)
            )
        ).all(),
        columns=["activity_id", "latitude", "longitude"],
    )
    return cluster_stays(stays)


def cluster_stays(stays: pd.DataFrame) -> list[ProposedPlace]:
    if stays.empty:
        return []
    x, y = compute_tile_float(
        stays["latitude"].to_numpy(), stays["longitude"].to_numpy(), CELL_ZOOM
    )
    stays = stays.assign(
        cell=stays.groupby([np.floor(x), np.floor(y)]).ngroup().to_numpy()
    )
    cells = stays.groupby("cell")
    cell_members = cells.indices
    cell_positions = cells[["latitude", "longitude"]].mean()

    clusters = cluster_routes(
        _neighbors(
            cell_positions["latitude"].to_numpy(),
            cell_positions["longitude"].to_numpy(),
        )
    )
    clustered = {id for cluster in clusters for id in cluster.member_ids}
    groups = [cluster.member_ids for cluster in clusters] + [
        [id] for id in range(len(cell_members)) if id not in clustered
    ]

    proposals = []
    for group in groups:
        members = stays.iloc[np.concatenate([cell_members[id] for id in group])]
        num_activities = members["activity_id"].nunique()
        if num_activities >= MIN_ACTIVITIES:
            proposals.append(
                ProposedPlace(
                    latitude=float(members["latitude"].mean()),
                    longitude=float(members["longitude"].mean()),
                    num_stays=len(members),
                    num_activities=num_activities,
                )
            )
    return sorted(proposals, key=lambda proposal: -proposal.num_activities)


def _neighbors(lat: np.ndarray, lon: np.ndarray) -> Neighbors:
    points = np.asarray(shapely.points(lon, lat))
    query_distance = PLACE_RADIUS_M / (METERS_PER_DEGREE * np.cos(np.radians(lat)))
    left, right = shapely.STRtree(points).query(
        points, predicate="dwithin", distance=query_distance
    )
    distinct = left != right
    left, right = left[distinct], right[distinct]
    distances = get_distance(lat[left], lon[left], lat[right], lon[right])
    neighbors: Neighbors = {}
    for a, b, distance_m in zip(left, right, distances):
        if distance_m <= PLACE_RADIUS_M:
            neighbors.setdefault(int(a), {})[int(b)] = float(distance_m)
            neighbors.setdefault(int(b), {})[int(a)] = float(distance_m)
    return neighbors
