import logging

import pandas as pd
import sqlalchemy as sa
from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.distance import DistanceMatcher
from tqdm import tqdm

from ...core.datamodel import (
    DB,
    Activity,
    get_activity_by_id,
    get_activity_ids,
    get_time_series,
)
from ...core.raster_map import GeoBounds
from ...core.tile_visits import _fallback_timestamp_for_activity
from .model import (
    SQL_IN_BATCH_SIZE,
    ActivityStreetChunkRun,
    StreetChunk,
    StreetChunkVisit,
)
from .osm_fetch import ensure_streets_for_bounds

logger = logging.getLogger(__name__)

BBOX_PADDING_DEG = 0.002
"""~200 m padding around an activity's bounding box, so streets just outside
the recorded track are still available for matching."""

# Map-matching tuning: GPS noise is typically single-digit to low double-digit
# metres, and streets close to the true path but more than ~50 m away should
# not be considered.
_OBS_NOISE_M = 10.0
_MAX_DIST_M = 50.0


def _activity_bounds(time_series: pd.DataFrame) -> GeoBounds | None:
    if time_series.empty:
        return None
    return GeoBounds(
        lat_min=time_series["latitude"].min() - BBOX_PADDING_DEG,
        lon_min=time_series["longitude"].min() - BBOX_PADDING_DEG,
        lat_max=time_series["latitude"].max() + BBOX_PADDING_DEG,
        lon_max=time_series["longitude"].max() + BBOX_PADDING_DEG,
    )


def _build_graph(
    bounds: GeoBounds,
) -> tuple[InMemMap, dict[frozenset, tuple[int, int, float]]]:
    """Build an in-memory routing graph from the `StreetChunk` rows overlapping
    `bounds`. Each chunk becomes one (bidirectional) graph edge; a chunk
    endpoint that coincides with a real OSM node has the exact same
    (lat, lon) in every way that shares it, which is what connects the graph
    across intersections without separate topology bookkeeping (see
    `osm_fetch._store_ways`).
    """
    rows = DB.session.execute(
        sa.select(
            StreetChunk.way_id,
            StreetChunk.seq,
            StreetChunk.lat1,
            StreetChunk.lon1,
            StreetChunk.lat2,
            StreetChunk.lon2,
            StreetChunk.length_m,
        ).where(
            sa.or_(
                sa.and_(
                    StreetChunk.lat1.between(bounds.lat_min, bounds.lat_max),
                    StreetChunk.lon1.between(bounds.lon_min, bounds.lon_max),
                ),
                sa.and_(
                    StreetChunk.lat2.between(bounds.lat_min, bounds.lat_max),
                    StreetChunk.lon2.between(bounds.lon_min, bounds.lon_max),
                ),
            )
        )
    ).all()

    graph = InMemMap("streets", use_latlon=True, use_rtree=False)
    edge_lookup: dict[frozenset, tuple[int, int, float]] = {}
    known_nodes: set[tuple[float, float]] = set()
    for way_id, seq, lat1, lon1, lat2, lon2, length_m in rows:
        a, b = (lat1, lon1), (lat2, lon2)
        if a not in known_nodes:
            graph.add_node(a, a)
            known_nodes.add(a)
        if b not in known_nodes:
            graph.add_node(b, b)
            known_nodes.add(b)
        graph.add_edge(a, b)
        graph.add_edge(b, a)
        edge_lookup[frozenset((a, b))] = (way_id, seq, length_m)
    return graph, edge_lookup


def _match_path_to_chunks(
    time_series: pd.DataFrame,
    graph: InMemMap,
    edge_lookup: dict[frozenset, tuple[int, int, float]],
) -> list[tuple[int, int]]:
    """Return the ordered sequence of (way_id, seq) chunks the track passes
    through, according to the best HMM-matched path."""
    path = list(zip(time_series["latitude"], time_series["longitude"]))
    if len(path) < 2:
        return []

    matcher = DistanceMatcher(
        graph,
        obs_noise=_OBS_NOISE_M,
        max_dist_init=_MAX_DIST_M,
        max_dist=_MAX_DIST_M,
        non_emitting_states=True,
    )
    try:
        matcher.match(path)
    except Exception:
        logger.warning("Map matching failed for a track.", exc_info=True)
        return []

    node_path = matcher.path_pred_onlynodes
    chunks: list[tuple[int, int]] = []
    for a, b in zip(node_path, node_path[1:]):
        if a == b:
            continue
        edge = edge_lookup.get(frozenset((a, b)))
        if edge is None:
            continue
        way_id, seq, _length_m = edge
        chunks.append((way_id, seq))
    return chunks


def _collapse_into_runs(
    chunks: list[tuple[int, int]],
) -> list[tuple[int, int, int]]:
    """Collapse a sequence of (way_id, seq) chunks into contiguous
    (way_id, seq_start, seq_end) runs, splitting on a way change or a gap."""
    runs: list[tuple[int, int, int]] = []
    current_way: int | None = None
    current_min = current_max = 0
    prev_seq: int | None = None
    for way_id, seq in chunks:
        same_run = (
            way_id == current_way and prev_seq is not None and abs(seq - prev_seq) == 1
        )
        if same_run:
            current_min = min(current_min, seq)
            current_max = max(current_max, seq)
        else:
            if current_way is not None:
                runs.append((current_way, current_min, current_max))
            current_way = way_id
            current_min = current_max = seq
        prev_seq = seq
    if current_way is not None:
        runs.append((current_way, current_min, current_max))
    return runs


def _update_chunk_visits(
    activity: Activity, way_id: int, seq_start: int, seq_end: int, time
) -> None:
    chunk_ids = DB.session.scalars(
        sa.select(StreetChunk.id).where(
            StreetChunk.way_id == way_id,
            StreetChunk.seq.between(seq_start, seq_end),
        )
    ).all()
    if not chunk_ids:
        return

    existing_by_chunk: dict[int, StreetChunkVisit] = {}
    for i in range(0, len(chunk_ids), SQL_IN_BATCH_SIZE):
        batch = chunk_ids[i : i + SQL_IN_BATCH_SIZE]
        for visit in DB.session.scalars(
            sa.select(StreetChunkVisit).where(StreetChunkVisit.chunk_id.in_(batch))
        ):
            existing_by_chunk[visit.chunk_id] = visit

    for chunk_id in chunk_ids:
        existing = existing_by_chunk.get(chunk_id)
        if existing is None:
            DB.session.add(
                StreetChunkVisit(
                    chunk_id=chunk_id,
                    first_activity_id=activity.id,
                    first_time=time,
                    last_activity_id=activity.id,
                    last_time=time,
                    visit_count=1,
                )
            )
            continue

        existing.visit_count += 1
        if time is not None and (
            existing.first_time is None or time < existing.first_time
        ):
            existing.first_activity_id = activity.id
            existing.first_time = time
        if time is not None and (
            existing.last_time is None or time > existing.last_time
        ):
            existing.last_activity_id = activity.id
            existing.last_time = time


def match_activity_to_streets(activity_id: int) -> None:
    activity = get_activity_by_id(activity_id)
    time_series = get_time_series(activity_id)
    bounds = _activity_bounds(time_series)
    if bounds is None:
        return

    ensure_streets_for_bounds(bounds)

    graph, edge_lookup = _build_graph(bounds)
    chunks = _match_path_to_chunks(time_series, graph, edge_lookup)
    runs = _collapse_into_runs(chunks)

    fallback_time = _fallback_timestamp_for_activity(activity)
    time = fallback_time.to_pydatetime() if fallback_time is not None else None

    for way_id, seq_start, seq_end in runs:
        DB.session.add(
            ActivityStreetChunkRun(
                way_id=way_id,
                seq_start=seq_start,
                seq_end=seq_end,
                activity_id=activity_id,
                time_start=time,
                time_end=time,
            )
        )
        _update_chunk_visits(activity, way_id, seq_start, seq_end, time)
    DB.session.commit()


def _processed_activity_ids() -> set[int]:
    return {
        row[0]
        for row in DB.session.query(ActivityStreetChunkRun.activity_id).distinct()
    }


def compute_street_visits_new() -> None:
    processed_ids = _processed_activity_ids()
    unprocessed_ids = [
        activity_id
        for activity_id in get_activity_ids()
        if activity_id not in processed_ids
    ]
    for activity_id in tqdm(unprocessed_ids, desc="Street visits", delay=1):
        try:
            match_activity_to_streets(activity_id)
        except Exception:
            logger.warning(
                "Street matching failed for activity %d.", activity_id, exc_info=True
            )
            DB.session.rollback()


def get_new_street_length_m_for_activity(activity_id: int) -> float:
    return (
        DB.session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(StreetChunk.length_m), 0.0))
            .select_from(StreetChunkVisit)
            .join(StreetChunk, StreetChunk.id == StreetChunkVisit.chunk_id)
            .where(StreetChunkVisit.first_activity_id == activity_id)
        )
        or 0.0
    )
