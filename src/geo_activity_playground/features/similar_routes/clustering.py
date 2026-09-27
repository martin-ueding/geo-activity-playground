"""Groups activities along the same route around a central activity.

Two activities are neighbors when both lie on each other within the maximum
distance. The activity with the most neighbors becomes the center of a cluster
with all its neighbors. These are removed and the procedure repeats. Unlike
single-linkage clustering, this doesn't chain slightly different routes into
one cluster, and every member is a direct neighbor of its center.
"""

import dataclasses

import sqlalchemy
from sqlalchemy.orm import aliased

from ...core.datamodel import DB
from .model import RouteDistance

type Neighbors = dict[int, dict[int, float]]


@dataclasses.dataclass
class RouteCluster:
    center_id: int
    distances_to_center_m: dict[int, float]

    @property
    def member_ids(self) -> list[int]:
        return list(self.distances_to_center_m)


def load_neighbors(quantile: str, max_distance_m: float) -> Neighbors:
    forward = aliased(RouteDistance)
    backward = aliased(RouteDistance)
    distance = sqlalchemy.func.max(
        getattr(forward, quantile), getattr(backward, quantile)
    )
    rows = DB.session.execute(
        sqlalchemy.select(forward.activity_id, forward.reference_activity_id, distance)
        .join(
            backward,
            (backward.activity_id == forward.reference_activity_id)
            & (backward.reference_activity_id == forward.activity_id),
        )
        .where(
            forward.activity_id < forward.reference_activity_id,
            distance.is_not(None),
            distance <= max_distance_m,
        )
    ).all()
    neighbors: Neighbors = {}
    for a, b, distance_m in rows:
        neighbors.setdefault(a, {})[b] = distance_m
        neighbors.setdefault(b, {})[a] = distance_m
    return neighbors


def cluster_routes(neighbors: Neighbors) -> list[RouteCluster]:
    remaining = {id: dict(others) for id, others in neighbors.items()}
    clusters = []
    while remaining:
        center_id = max(
            remaining,
            key=lambda id: (len(remaining[id]), -sum(remaining[id].values()), -id),
        )
        if not remaining[center_id]:
            break
        distances = {center_id: 0.0} | dict(
            sorted(remaining[center_id].items(), key=lambda item: item[1])
        )
        clusters.append(RouteCluster(center_id, distances))
        for id in distances:
            del remaining[id]
        for others in remaining.values():
            for id in distances:
                others.pop(id, None)
    return clusters


def find_cluster(clusters: list[RouteCluster], activity_id: int) -> RouteCluster | None:
    for cluster in clusters:
        if activity_id in cluster.distances_to_center_m:
            return cluster
    return None
