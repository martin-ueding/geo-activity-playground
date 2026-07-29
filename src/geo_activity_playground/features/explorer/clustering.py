import itertools
import json
import logging

import pandas as pd
import sqlalchemy as sa
from tqdm import tqdm

from ...core.datamodel import DB, UiConfig
from ...core.tile_visits import get_tile_history_df
from ...core.tiles import adjacent_to
from .model import (
    ClusterHistoryCheckpoint,
    ClusterHistoryEvent,
    ClusterMembership,
    ClusterSizeHistory,
    ExplorerSquare,
    SquareHistory,
)

logger = logging.getLogger(__name__)


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


def compute_tile_evolution(config: UiConfig) -> None:
    for zoom in config.explorer_zoom_levels:
        # Get tile history from database
        tile_history = get_tile_history_df(zoom)
        rebuild_cluster_history_for_zoom(zoom, tile_history)
        # Recompute from the full history each time and persist to the database.
        state = TileEvolutionState()
        _compute_cluster_evolution(tile_history, state, zoom)
        _compute_square_history(tile_history, state, zoom)
        _persist_evolution_to_db(zoom, state)


def _persist_evolution_to_db(zoom: int, state: "TileEvolutionState") -> None:
    """Write the square state and evolution plot series of a zoom to the database."""
    DB.session.query(ExplorerSquare).filter(ExplorerSquare.zoom == zoom).delete()
    DB.session.query(SquareHistory).filter(SquareHistory.zoom == zoom).delete()
    DB.session.query(ClusterSizeHistory).filter(
        ClusterSizeHistory.zoom == zoom
    ).delete()

    DB.session.add(
        ExplorerSquare(
            zoom=zoom,
            square_x=state.square_x,
            square_y=state.square_y,
            max_square_size=state.max_square_size,
        )
    )

    for row in state.square_evolution.itertuples(index=False):
        DB.session.add(
            SquareHistory(
                zoom=zoom,
                time=(row.time.to_pydatetime() if pd.notna(row.time) else None),
                max_square_size=int(row.max_square_size),
                square_x=int(row.square_x),
                square_y=int(row.square_y),
            )
        )

    for row in state.cluster_evolution.itertuples(index=False):
        DB.session.add(
            ClusterSizeHistory(
                zoom=zoom,
                time=(row.time.to_pydatetime() if pd.notna(row.time) else None),
                max_cluster_size=int(row.max_cluster_size),
            )
        )

    DB.session.commit()


def get_explorer_square(zoom: int) -> tuple[int | None, int | None, int]:
    """Return ``(square_x, square_y, max_square_size)`` for a zoom level."""
    row = DB.session.get(ExplorerSquare, zoom)
    if row is None:
        return None, None, 0
    return row.square_x, row.square_y, row.max_square_size


def get_square_history_df(zoom: int) -> pd.DataFrame:
    """Square evolution series for the plot: time, max_square_size, square_x/y."""
    rows = DB.session.execute(
        sa.select(
            SquareHistory.time,
            SquareHistory.max_square_size,
            SquareHistory.square_x,
            SquareHistory.square_y,
        )
        .where(SquareHistory.zoom == zoom)
        .order_by(SquareHistory.id)
    ).all()
    return pd.DataFrame(
        {
            "time": [pd.Timestamp(r.time) if r.time else pd.NaT for r in rows],
            "max_square_size": [r.max_square_size for r in rows],
            "square_x": [r.square_x for r in rows],
            "square_y": [r.square_y for r in rows],
        }
    )


def get_cluster_size_history_df(zoom: int) -> pd.DataFrame:
    """Cluster size evolution series for the plot: time, max_cluster_size."""
    rows = DB.session.execute(
        sa.select(ClusterSizeHistory.time, ClusterSizeHistory.max_cluster_size)
        .where(ClusterSizeHistory.zoom == zoom)
        .order_by(ClusterSizeHistory.id)
    ).all()
    return pd.DataFrame(
        {
            "time": [pd.Timestamp(r.time) if r.time else pd.NaT for r in rows],
            "max_cluster_size": [r.max_cluster_size for r in rows],
        }
    )


def rebuild_cluster_history_for_zoom(zoom: int, tile_history: pd.DataFrame) -> None:
    DB.session.query(ClusterHistoryEvent).filter(
        ClusterHistoryEvent.zoom == zoom
    ).delete()
    DB.session.query(ClusterHistoryCheckpoint).filter(
        ClusterHistoryCheckpoint.zoom == zoom
    ).delete()
    DB.session.query(ClusterMembership).filter(ClusterMembership.zoom == zoom).delete()

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

    _materialize_cluster_membership(zoom, state)

    DB.session.commit()


def _materialize_cluster_membership(zoom: int, state: ClusterReplayState) -> None:
    """Persist the final cluster membership of a replay state for a zoom level."""
    batch: list[ClusterMembership] = []
    for tile in state.cluster_tiles:
        root = _find_root(state.parents, tile)
        batch.append(
            ClusterMembership(
                zoom=zoom,
                tile_x=tile[0],
                tile_y=tile[1],
                cluster_x=root[0],
                cluster_y=root[1],
            )
        )
        if len(batch) >= 1_000:
            DB.session.add_all(batch)
            batch = []
    if batch:
        DB.session.add_all(batch)


def get_cluster_membership_in_bounds(
    zoom: int, x_min: int, x_max: int, y_min: int, y_max: int
) -> dict[tuple[int, int], tuple[int, int]]:
    """Return ``tile -> representative tile`` for cluster tiles within a viewport."""
    rows = DB.session.execute(
        sa.select(
            ClusterMembership.tile_x,
            ClusterMembership.tile_y,
            ClusterMembership.cluster_x,
            ClusterMembership.cluster_y,
        ).where(
            ClusterMembership.zoom == zoom,
            ClusterMembership.tile_x >= x_min,
            ClusterMembership.tile_x <= x_max,
            ClusterMembership.tile_y >= y_min,
            ClusterMembership.tile_y <= y_max,
        )
    ).all()
    return {(row.tile_x, row.tile_y): (row.cluster_x, row.cluster_y) for row in rows}


def get_cluster_tile_count(zoom: int) -> int:
    """Number of tiles that belong to any cluster at a zoom level."""
    return (
        DB.session.query(ClusterMembership)
        .filter(ClusterMembership.zoom == zoom)
        .count()
    )


def get_max_cluster(zoom: int) -> tuple[tuple[int, int] | None, int]:
    """Return the representative and size of the largest cluster at a zoom level."""
    row = DB.session.execute(
        sa.select(
            ClusterMembership.cluster_x,
            ClusterMembership.cluster_y,
            sa.func.count().label("size"),
        )
        .where(ClusterMembership.zoom == zoom)
        .group_by(ClusterMembership.cluster_x, ClusterMembership.cluster_y)
        .order_by(sa.desc("size"))
        .limit(1)
    ).first()
    if row is None:
        return None, 0
    return (row.cluster_x, row.cluster_y), int(row.size)


def get_cluster_id_for_tile(
    zoom: int, tile_x: int, tile_y: int
) -> tuple[int, int] | None:
    """Return the representative tile of the cluster a tile belongs to, if any."""
    row = DB.session.execute(
        sa.select(ClusterMembership.cluster_x, ClusterMembership.cluster_y).where(
            ClusterMembership.zoom == zoom,
            ClusterMembership.tile_x == tile_x,
            ClusterMembership.tile_y == tile_y,
        )
    ).first()
    if row is None:
        return None
    return (row.cluster_x, row.cluster_y)


def get_cluster_members(
    zoom: int, cluster_x: int, cluster_y: int
) -> list[tuple[int, int]]:
    """Return all member tiles of a cluster identified by its representative."""
    rows = DB.session.execute(
        sa.select(ClusterMembership.tile_x, ClusterMembership.tile_y).where(
            ClusterMembership.zoom == zoom,
            ClusterMembership.cluster_x == cluster_x,
            ClusterMembership.cluster_y == cluster_y,
        )
    ).all()
    return [(row.tile_x, row.tile_y) for row in rows]


def get_biggest_cluster_members(zoom: int) -> list[tuple[int, int]]:
    """Return the member tiles of the largest cluster at a zoom level."""
    representative, _size = get_max_cluster(zoom)
    if representative is None:
        return []
    return get_cluster_members(zoom, representative[0], representative[1])


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
