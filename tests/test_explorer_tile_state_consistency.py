import datetime as dt
import json
import random
import time
import uuid
from types import SimpleNamespace

import pandas as pd
import sqlalchemy as sa

import geo_activity_playground.features.explorer.filtered as filtered_module
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.coordinates import Bounds
from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    ActivityTile,
    Kind,
    TileVisit,
    get_activity_ids,
)
from geo_activity_playground.core.raster_map import OSM_TILE_SIZE
from geo_activity_playground.core.tile_visits import (
    _consistency_check,
    _process_activity,
    _tiles_from_points,
    get_activity_ids_in_tile,
    get_tile_count,
    get_tile_history_df,
    get_tile_visits_in_bounds,
    get_visited_tiles,
    rebuild_tile_visits_from_activity_tiles,
    refresh_tile_visits_for_activity,
    remove_activity_from_tile_state,
)
from geo_activity_playground.features.explorer.clustering import (
    CLUSTER_HISTORY_CLAIM_TIMEOUT,
    TileEvolutionState,
    _claim_cluster_history_rebuild,
    _compute_cluster_evolution,
    _compute_square_history,
    _find_root,
    compute_current_cluster_state,
    compute_current_state_for_zoom,
    compute_max_square,
    get_cluster_history_latest_event_index,
    get_cluster_id_for_tile,
    get_cluster_size_history_df,
    get_cluster_tile_activations_df,
    get_cluster_tile_count,
    get_cluster_tiles_at_cutoff,
    get_cluster_tiles_gained_by_activity,
    get_covered_tiles,
    get_square_history_df,
    is_cluster_history_stale,
    mark_cluster_history_stale,
    rebuild_cluster_history,
    rebuild_cluster_history_for_zoom,
    rebuild_cluster_history_if_stale,
)
from geo_activity_playground.features.explorer.filtered import (
    delete_outdated_filtered_cluster_cache,
    delete_stale_filtered_cluster_cache,
    get_filtered_cluster_cache_stats,
    get_filtered_cluster_state,
    get_filtered_tile_visits_in_bounds,
)
from geo_activity_playground.features.explorer.model import (
    ClusterHistoryEvent,
    ClusterHistoryStatus,
    ClusterTileActivation,
    FilteredClusterCache,
    InaccessibleTile,
)
from geo_activity_playground.features.heatmap.blueprint import _get_counts


def test_get_tile_visits_uses_db_only(app) -> None:
    with app.app_context():
        activity = Activity(id=1, name="Ride")
        DB.session.add(activity)
        DB.session.add(
            TileVisit(
                zoom=14,
                tile_x=3,
                tile_y=4,
                first_activity_id=1,
                first_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                last_activity_id=1,
                last_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                visit_count=1,
            )
        )
        DB.session.commit()

        visits = get_tile_visits_in_bounds(14, 3, 3, 4, 4)
        assert (3, 4) in visits
        assert visits[(3, 4)]["visit_count"] == 1


def test_get_tile_visits_falls_back_to_activity_start_when_time_missing(app) -> None:
    with app.app_context():
        activity = Activity(id=1, name="Ride", start=dt.datetime(2026, 1, 1, 10, 0, 0))
        DB.session.add(activity)
        DB.session.add(
            TileVisit(
                zoom=14,
                tile_x=8,
                tile_y=9,
                first_activity_id=1,
                first_time=None,
                last_activity_id=1,
                last_time=None,
                visit_count=1,
            )
        )
        DB.session.commit()

        visits = get_tile_visits_in_bounds(14, 8, 8, 9, 9)
        assert visits[(8, 9)]["first_time"] == pd.Timestamp("2026-01-01T10:00:00")
        assert visits[(8, 9)]["last_time"] == pd.Timestamp("2026-01-01T10:00:00")


def test_remove_activity_from_tile_state_removes_all_references(app) -> None:
    with app.app_context():
        DB.session.add_all([Activity(id=1, name="A1"), Activity(id=2, name="A2")])
        DB.session.add_all(
            [
                ActivityTile(zoom=17, tile_x=1, tile_y=2, activity_id=1),
                ActivityTile(zoom=17, tile_x=1, tile_y=2, activity_id=2),
                ActivityTile(zoom=17, tile_x=2, tile_y=3, activity_id=2),
                ActivityTile(zoom=18, tile_x=4, tile_y=5, activity_id=2),
            ]
        )
        DB.session.commit()

        removed = remove_activity_from_tile_state(2)

        assert removed == 3
        assert get_activity_ids_in_tile(17, 1, 2) == {1}
        assert get_activity_ids_in_tile(17, 2, 3) == set()
        assert get_activity_ids_in_tile(18, 4, 5) == set()


def test_heatmap_counts_skip_deleted_activity_ids(app) -> None:
    with app.app_context():
        activity = Activity(id=1, name="Ride", time_series_uuid=str(uuid.uuid4()))
        DB.session.add(activity)
        DB.session.flush()
        activity.replace_time_series(
            pd.DataFrame({"x": [0.5], "y": [0.5], "segment_id": [0]})
        )
        DB.session.add_all(
            [
                ActivityTile(zoom=17, tile_x=1, tile_y=2, activity_id=1),
                # Activity 2 has no matching Activity row, simulating deletion.
                ActivityTile(zoom=17, tile_x=1, tile_y=2, activity_id=2),
            ]
        )
        DB.session.commit()

        config = SimpleNamespace(heatmap_cache_min_activities=0)
        # get_time_series(2) raises because the activity was deleted; _get_counts
        # must skip it and still return counts without error.
        counts = _get_counts(1, 2, 17, {}, config)
        assert counts.shape == (OSM_TILE_SIZE, OSM_TILE_SIZE)


def test_process_activity_updates_first_and_last_fields_in_db(app) -> None:
    with app.app_context():
        older = Activity(id=1, name="Older", time_series_uuid=str(uuid.uuid4()))
        newer = Activity(id=2, name="Newer", time_series_uuid=str(uuid.uuid4()))
        DB.session.add_all([older, newer])
        DB.session.flush()
        older.replace_time_series(
            pd.DataFrame(
                {
                    "time": [pd.Timestamp("2024-01-01T10:00:00Z")],
                    "x": [0.25],
                    "y": [0.25],
                    "segment_id": [0],
                }
            )
        )
        newer.replace_time_series(
            pd.DataFrame(
                {
                    "time": [pd.Timestamp("2024-01-02T10:00:00Z")],
                    "x": [0.25],
                    "y": [0.25],
                    "segment_id": [0],
                }
            )
        )
        DB.session.commit()

        _process_activity(2)
        _process_activity(1)

        visit = DB.session.scalar(
            sa.select(TileVisit).where(
                TileVisit.zoom == 14,
                TileVisit.tile_x == 4096,
                TileVisit.tile_y == 4096,
            )
        )
        assert visit is not None
        assert visit.visit_count == 2
        assert visit.first_activity_id == 1
        assert visit.last_activity_id == 2


def test_tiles_from_points_localizes_naive_time_series() -> None:
    df = pd.DataFrame(
        {
            "time": [pd.Timestamp("2026-01-01T12:00:00")],
            "x": [0.1],
            "y": [0.2],
            "segment_id": [0],
        }
    )
    rows = list(_tiles_from_points(df, 14))
    assert rows
    assert rows[0][0].tzinfo is not None


def test_process_activity_prefers_non_missing_time_for_same_tile(app) -> None:
    with app.app_context():
        activity = Activity(
            id=1, name="Mixed Time Activity", time_series_uuid=str(uuid.uuid4())
        )
        DB.session.add(activity)
        DB.session.flush()
        activity.replace_time_series(
            pd.DataFrame(
                {
                    "time": [pd.NaT, pd.Timestamp("2024-01-01T10:00:00Z")],
                    "x": [0.25, 0.25],
                    "y": [0.25, 0.25],
                    "segment_id": [0, 0],
                }
            )
        )
        DB.session.commit()

        _process_activity(1)

        visit = DB.session.scalar(
            sa.select(TileVisit).where(
                TileVisit.zoom == 14,
                TileVisit.tile_x == 4096,
                TileVisit.tile_y == 4096,
            )
        )
        assert visit is not None
        assert visit.first_time is not None
        assert visit.last_time is not None


def test_process_activity_uses_activity_start_when_track_times_missing(app) -> None:
    with app.app_context():
        no_track_times = Activity(
            id=1,
            name="No Track Times",
            start=dt.datetime(2024, 1, 1, 9, 0, 0),
            time_series_uuid=str(uuid.uuid4()),
        )
        later_visit = Activity(
            id=2,
            name="Later Visit",
            start=dt.datetime(2024, 1, 2, 9, 0, 0),
            time_series_uuid=str(uuid.uuid4()),
        )
        DB.session.add_all([no_track_times, later_visit])
        DB.session.flush()
        no_track_times.replace_time_series(
            pd.DataFrame(
                {
                    "time": [pd.NaT],
                    "x": [0.25],
                    "y": [0.25],
                    "segment_id": [0],
                }
            )
        )
        later_visit.replace_time_series(
            pd.DataFrame(
                {
                    "time": [pd.Timestamp("2024-01-02T09:00:00Z")],
                    "x": [0.25],
                    "y": [0.25],
                    "segment_id": [0],
                }
            )
        )
        DB.session.commit()

        _process_activity(1)
        _process_activity(2)

        visit = DB.session.scalar(
            sa.select(TileVisit).where(
                TileVisit.zoom == 14,
                TileVisit.tile_x == 4096,
                TileVisit.tile_y == 4096,
            )
        )
        assert visit is not None
        assert visit.first_activity_id == 1
        assert visit.first_time == dt.datetime(2024, 1, 1, 9, 0, 0)
        assert visit.last_activity_id == 2
        assert visit.last_time == dt.datetime(2024, 1, 2, 9, 0, 0)


def test_cluster_evolution_only_records_new_max_values() -> None:
    first_pair = [
        (-1, 0),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 1),
        (2, 0),
        (0, 0),
        (1, 0),
    ]
    second_pair = [(x + 20, y) for x, y in first_pair]
    points = first_pair + second_pair
    tiles = pd.DataFrame(
        {
            "activity_id": list(range(1, len(points) + 1)),
            "time": pd.date_range(
                "2026-01-01", periods=len(points), tz="UTC", freq="h"
            ),
            "tile_x": [x for x, _ in points],
            "tile_y": [y for _, y in points],
        }
    )
    state = TileEvolutionState()
    _compute_cluster_evolution(tiles, state, 14)
    assert list(state.cluster_evolution["max_cluster_size"]) == [2]


def test_deterministic_ordering_for_activity_and_tile_history(app) -> None:
    with app.app_context():
        DB.session.add_all(
            [
                Activity(id=2, name="Second", start=dt.datetime(2026, 1, 1, 10, 0, 0)),
                Activity(id=1, name="First", start=dt.datetime(2026, 1, 1, 10, 0, 0)),
            ]
        )
        DB.session.commit()
        assert get_activity_ids() == [1, 2]

        DB.session.add_all(
            [
                TileVisit(
                    zoom=14,
                    tile_x=2,
                    tile_y=1,
                    first_activity_id=2,
                    first_time=dt.datetime(2026, 1, 1, 11, 0, 0),
                    last_activity_id=2,
                    last_time=dt.datetime(2026, 1, 1, 11, 0, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=1,
                    tile_y=1,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 11, 0, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 11, 0, 0),
                    visit_count=1,
                ),
            ]
        )
        DB.session.commit()

        history = get_tile_history_df(14)
        assert history.iloc[0]["activity_id"] == 1
        assert tuple(history.iloc[0][["tile_x", "tile_y"]]) == (1, 1)


def test_cluster_history_projection_records_every_event(app) -> None:
    with app.app_context():
        activity = Activity(id=1, name="Ride")
        DB.session.add(activity)
        for i in range(1_005):
            DB.session.add(
                TileVisit(
                    zoom=14,
                    tile_x=i,
                    tile_y=0,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 10, 0, 0)
                    + dt.timedelta(seconds=i),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 10, 0, 0)
                    + dt.timedelta(seconds=i),
                    visit_count=1,
                )
            )
        DB.session.commit()

        history = get_tile_history_df(14)
        rebuild_cluster_history_for_zoom(14, history)

        assert DB.session.query(ClusterHistoryEvent).filter(
            ClusterHistoryEvent.zoom == 14
        ).count() == len(history)
        # A single row of tiles never has four neighbors, so nothing clusters.
        assert (
            DB.session.query(ClusterTileActivation)
            .filter(ClusterTileActivation.zoom == 14)
            .count()
            == 0
        )


def test_cluster_history_diff_for_activity(app) -> None:
    with app.app_context():
        DB.session.add_all([Activity(id=1, name="A1"), Activity(id=2, name="A2")])
        DB.session.add_all(
            [
                TileVisit(
                    zoom=14,
                    tile_x=-1,
                    tile_y=0,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=-1,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 10, 1, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 10, 1, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=1,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 10, 2, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 10, 2, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=1,
                    tile_y=0,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 10, 3, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 10, 3, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=0,
                    first_activity_id=2,
                    first_time=dt.datetime(2026, 1, 1, 10, 4, 0),
                    last_activity_id=2,
                    last_time=dt.datetime(2026, 1, 1, 10, 4, 0),
                    visit_count=1,
                ),
            ]
        )
        DB.session.commit()

        history = get_tile_history_df(14)
        rebuild_cluster_history_for_zoom(14, history)
        before = get_cluster_tiles_at_cutoff(14, 4)
        after = get_cluster_tiles_at_cutoff(14, 5)
        added = get_cluster_tiles_gained_by_activity(14, 2)

        assert (0, 0) not in before
        assert (0, 0) in after
        assert added == {(0, 0)}
        assert get_cluster_tiles_gained_by_activity(14, 1) == set()


def test_cluster_tile_activations_use_activation_time_not_first_visit(app) -> None:
    with app.app_context():
        DB.session.add_all(
            [
                Activity(id=1, name="A1"),
                Activity(id=2, name="A2"),
                Activity(id=3, name="A3"),
                Activity(id=4, name="A4"),
                Activity(id=5, name="A5"),
            ]
        )
        DB.session.add_all(
            [
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=0,
                    first_activity_id=1,
                    first_time=dt.datetime(2025, 6, 1, 10, 0, 0),
                    last_activity_id=1,
                    last_time=dt.datetime(2025, 6, 1, 10, 0, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=-1,
                    tile_y=0,
                    first_activity_id=2,
                    first_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                    last_activity_id=2,
                    last_time=dt.datetime(2026, 1, 1, 10, 0, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=-1,
                    first_activity_id=3,
                    first_time=dt.datetime(2026, 1, 1, 10, 1, 0),
                    last_activity_id=3,
                    last_time=dt.datetime(2026, 1, 1, 10, 1, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=0,
                    tile_y=1,
                    first_activity_id=4,
                    first_time=dt.datetime(2026, 1, 1, 10, 2, 0),
                    last_activity_id=4,
                    last_time=dt.datetime(2026, 1, 1, 10, 2, 0),
                    visit_count=1,
                ),
                TileVisit(
                    zoom=14,
                    tile_x=1,
                    tile_y=0,
                    first_activity_id=5,
                    first_time=dt.datetime(2026, 1, 1, 10, 3, 0),
                    last_activity_id=5,
                    last_time=dt.datetime(2026, 1, 1, 10, 3, 0),
                    visit_count=1,
                ),
            ]
        )
        DB.session.commit()

        history = get_tile_history_df(14)
        rebuild_cluster_history_for_zoom(14, history)
        activations = get_cluster_tile_activations_df(14)

        center = activations.loc[
            (activations["tile_x"] == 0) & (activations["tile_y"] == 0)
        ]
        assert len(center) == 1
        assert center.iloc[0]["time"].year == 2026
        assert center.iloc[0]["activity_id"] == 5


def test_cluster_history_replay_latency_bound(app) -> None:
    with app.app_context():
        activity = Activity(id=1, name="Ride")
        DB.session.add(activity)
        for i in range(2_000):
            DB.session.add(
                TileVisit(
                    zoom=14,
                    tile_x=i,
                    tile_y=0,
                    first_activity_id=1,
                    first_time=dt.datetime(2026, 1, 1, 10, 0, 0)
                    + dt.timedelta(seconds=i),
                    last_activity_id=1,
                    last_time=dt.datetime(2026, 1, 1, 10, 0, 0)
                    + dt.timedelta(seconds=i),
                    visit_count=1,
                )
            )
        DB.session.commit()

        history = get_tile_history_df(14)
        rebuild_cluster_history_for_zoom(14, history)

        start = time.perf_counter()
        _ = get_cluster_tiles_at_cutoff(14, 2_000)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0


def _partition(state) -> set[frozenset[tuple[int, int]]]:
    """Cluster membership as a partition, ignoring which tile represents it."""
    groups: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for tile in state.cluster_tiles:
        groups.setdefault(_find_root(state.parents, tile), set()).add(tile)
    return {frozenset(members) for members in groups.values()}


def _add_tile_visits(tiles: list[tuple[int, int]], zoom: int = 14) -> None:
    """Store tiles as visits, one second apart, so the history has an order."""
    DB.session.add(Activity(id=1, name="Ride"))
    for i, (tile_x, tile_y) in enumerate(tiles):
        moment = dt.datetime(2026, 1, 1, 10, 0, 0) + dt.timedelta(seconds=i)
        DB.session.add(
            TileVisit(
                zoom=zoom,
                tile_x=tile_x,
                tile_y=tile_y,
                first_activity_id=1,
                first_time=moment,
                last_activity_id=1,
                last_time=moment,
                visit_count=1,
            )
        )
    DB.session.commit()


# A 5x5 block with a hole, a detached 4x4 block, and a bridge between them. The
# hole and the bridge make cluster membership and the biggest square disagree,
# which is what makes this a meaningful comparison.
_MIXED_TILES = (
    [(x, y) for x in range(5) for y in range(5) if (x, y) != (2, 2)]
    + [(x, y) for x in range(9, 13) for y in range(9, 13)]
    + [(x, 6) for x in range(5, 10)]
)


def test_current_state_matches_history_replay(app) -> None:
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)

        history = get_tile_history_df(14)
        rebuild_cluster_history_for_zoom(14, history)
        replayed = get_cluster_tiles_at_cutoff(14, len(history))

        current = compute_current_cluster_state(
            {(tile_x, tile_y) for tile_x, tile_y in _MIXED_TILES}
        )

        assert current.cluster_tiles == replayed
        assert current.cluster_tiles


def test_current_state_partition_is_order_independent(app) -> None:
    with app.app_context():
        forward = compute_current_cluster_state(_MIXED_TILES)
        backward = compute_current_cluster_state(list(reversed(_MIXED_TILES)))

        assert _partition(forward) == _partition(backward)
        assert forward.max_cluster_size == backward.max_cluster_size


def test_max_square_matches_incremental_history(app) -> None:
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)

        state = TileEvolutionState()
        _compute_square_history(get_tile_history_df(14), state, 14)

        square_x, square_y, size = compute_max_square(_MIXED_TILES)

        assert size == state.max_square_size
        covered = set(_MIXED_TILES)
        assert all(
            (square_x + dx, square_y + dy) in covered
            for dx in range(size)
            for dy in range(size)
        )


def test_max_square_is_empty_without_tiles(app) -> None:
    with app.app_context():
        assert compute_max_square([]) == (None, None, 0)


def test_max_square_matches_incremental_algorithm_on_random_sets() -> None:
    """The from-scratch recurrence must agree with the incremental scan."""
    rng = random.Random(20260808)
    for _ in range(30):
        tiles = sorted(
            {
                (rng.randrange(0, 12), rng.randrange(0, 12))
                for _ in range(rng.randrange(20, 120))
            }
        )
        frame = pd.DataFrame(
            {
                "tile_x": [tile[0] for tile in tiles],
                "tile_y": [tile[1] for tile in tiles],
                "time": [pd.Timestamp("2026-01-01T10:00:00")] * len(tiles),
            }
        )
        reference = TileEvolutionState()
        _compute_square_history(frame, reference, 14)

        _x, _y, size = compute_max_square(tiles)
        assert size == reference.max_square_size, tiles


def test_cluster_history_starts_stale_and_clears_after_rebuild(app) -> None:
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)

        assert is_cluster_history_stale(14)
        assert rebuild_cluster_history_if_stale(14) is True
        assert not is_cluster_history_stale(14)
        # A second call is a no-op, so pages do not pay for the replay again.
        assert rebuild_cluster_history_if_stale(14) is False

        assert (
            DB.session.query(ClusterTileActivation)
            .filter(ClusterTileActivation.zoom == 14)
            .count()
            > 0
        )

        mark_cluster_history_stale([14])
        assert is_cluster_history_stale(14)


def test_evolution_plot_endpoint_rebuilds_stale_history(app) -> None:
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)
        assert is_cluster_history_stale(14)

    client = app.test_client()
    response = client.get("/explorer/14/evolution/cluster.json")

    assert response.status_code == 200
    assert response.json["spec"] is not None
    with app.app_context():
        assert not is_cluster_history_stale(14)


# A plus shape: the center (0, 0) has all four neighbors, except that (1, 0) is
# a lake that can never be ridden. Without counting it, nothing clusters.
_PLUS_VISITED = [(0, 0), (-1, 0), (0, 1), (0, -1)]
_LAKE_TILE = (1, 0)


def _enable_counting_inaccessible() -> None:
    ConfigAccessor().ui().count_inaccessible_in_cluster = True
    DB.session.commit()


def test_inaccessible_tiles_do_not_count_by_default(app) -> None:
    with app.app_context():
        _add_tile_visits(_PLUS_VISITED)
        DB.session.add(
            InaccessibleTile(zoom=14, tile_x=_LAKE_TILE[0], tile_y=_LAKE_TILE[1])
        )
        DB.session.commit()

        assert get_covered_tiles(14) == set(_PLUS_VISITED)
        compute_current_state_for_zoom(14)
        assert get_cluster_tile_count(14) == 0


def test_inaccessible_tiles_complete_a_cluster_when_enabled(app) -> None:
    with app.app_context():
        _add_tile_visits(_PLUS_VISITED)
        DB.session.add(
            InaccessibleTile(zoom=14, tile_x=_LAKE_TILE[0], tile_y=_LAKE_TILE[1])
        )
        DB.session.commit()
        _enable_counting_inaccessible()

        assert get_covered_tiles(14) == set(_PLUS_VISITED) | {_LAKE_TILE}
        compute_current_state_for_zoom(14)
        assert get_cluster_id_for_tile(14, 0, 0) is not None
        # The lake itself is not visited, so it must not inflate the tile count.
        assert get_tile_count(14) == len(_PLUS_VISITED)


def test_inaccessible_tiles_extend_the_square_when_enabled(app) -> None:
    with app.app_context():
        square = [(x, y) for x in range(3) for y in range(3) if (x, y) != (1, 1)]
        _add_tile_visits(square)
        DB.session.add(InaccessibleTile(zoom=14, tile_x=1, tile_y=1))
        DB.session.commit()

        assert compute_max_square(get_covered_tiles(14))[2] == 1

        _enable_counting_inaccessible()
        assert compute_max_square(get_covered_tiles(14))[2] == 3


def test_inaccessible_tiles_are_seeded_at_the_origin_of_time(app) -> None:
    with app.app_context():
        _add_tile_visits(_PLUS_VISITED)
        DB.session.add(
            InaccessibleTile(zoom=14, tile_x=_LAKE_TILE[0], tile_y=_LAKE_TILE[1])
        )
        DB.session.commit()
        _enable_counting_inaccessible()

        rebuild_cluster_history(14)

        # The center clusters on the last visit, not before it.
        assert (0, 0) not in get_cluster_tiles_at_cutoff(14, 3)
        assert (0, 0) in get_cluster_tiles_at_cutoff(14, 4)
        # The lake was never ridden, so no activity may claim it.
        activation = DB.session.scalar(
            sa.select(ClusterTileActivation).where(
                ClusterTileActivation.zoom == 14,
                ClusterTileActivation.tile_x == 0,
                ClusterTileActivation.tile_y == 0,
            )
        )
        assert activation is not None
        assert activation.activity_id == 1


def test_current_state_and_history_agree_with_inaccessible_tiles(app) -> None:
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)
        # Fill the hole of the 5x5 block and one bridge gap.
        for tile in [(2, 2), (5, 5)]:
            DB.session.add(InaccessibleTile(zoom=14, tile_x=tile[0], tile_y=tile[1]))
        DB.session.commit()
        _enable_counting_inaccessible()

        rebuild_cluster_history(14)
        replayed = get_cluster_tiles_at_cutoff(
            14, get_cluster_history_latest_event_index(14)
        )
        current = compute_current_cluster_state(get_covered_tiles(14))

        assert current.cluster_tiles == replayed


def _add_activity_tiles(activity_id: int, kind: Kind, tiles, start) -> None:
    DB.session.add(
        Activity(id=activity_id, name=f"A{activity_id}", kind=kind, start=start)
    )
    for tile_x, tile_y in tiles:
        DB.session.add(
            ActivityTile(
                zoom=14,
                tile_x=tile_x,
                tile_y=tile_y,
                activity_id=activity_id,
                time=start,
            )
        )
    DB.session.commit()


def test_explorer_filter_excludes_kinds_from_tile_visits(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        train = Kind(name="Train")
        DB.session.add_all([ride, train])
        DB.session.commit()

        _add_activity_tiles(1, ride, [(0, 0), (1, 0)], dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, train, [(5, 5), (6, 5)], dt.datetime(2026, 1, 2))

        rebuild_tile_visits_from_activity_tiles()
        assert get_visited_tiles(14) == {(0, 0), (1, 0), (5, 5), (6, 5)}

        ConfigAccessor().ui().explorer_filter_json = json.dumps({"kind": [ride.id]})
        DB.session.commit()
        rebuild_tile_visits_from_activity_tiles()

        assert get_visited_tiles(14) == {(0, 0), (1, 0)}


def test_filtered_cluster_state_is_smaller_than_unfiltered(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        train = Kind(name="Train")
        DB.session.add_all([ride, train])
        DB.session.commit()

        # The ride alone leaves a plus shape that does not cluster; the train
        # supplies the fourth neighbor of the center.
        _add_activity_tiles(1, ride, _PLUS_VISITED, dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, train, [(1, 0)], dt.datetime(2026, 1, 2))

        both = get_filtered_cluster_state(14, frozenset({1, 2}))
        ride_only = get_filtered_cluster_state(14, frozenset({1}))

        assert (0, 0) in both.membership
        assert ride_only.membership == {}
        assert both.num_cluster_tiles > ride_only.num_cluster_tiles


def test_filtered_tile_visits_respect_the_activity_set(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()
        _add_activity_tiles(1, ride, [(0, 0)], dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, ride, [(0, 0), (1, 0)], dt.datetime(2026, 1, 2))

        bounds = Bounds(0, 0, 4, 4)
        both = get_filtered_tile_visits_in_bounds(14, bounds, frozenset({1, 2}))
        assert both[(0, 0)]["visit_count"] == 2
        assert both[(0, 0)]["first_id"] == 1

        second = get_filtered_tile_visits_in_bounds(14, bounds, frozenset({2}))
        assert second[(0, 0)]["visit_count"] == 1
        assert second[(0, 0)]["first_id"] == 2


def test_explorer_page_counters_follow_the_search_filter(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        train = Kind(name="Train")
        DB.session.add_all([ride, train])
        DB.session.commit()
        _add_activity_tiles(1, ride, _PLUS_VISITED, dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, train, [(1, 0), (2, 0)], dt.datetime(2026, 1, 2))
        rebuild_tile_visits_from_activity_tiles()
        compute_current_state_for_zoom(14)
        ride_id = ride.id

    client = app.test_client()
    unfiltered = client.get("/explorer/14/server-side")
    filtered = client.get(f"/explorer/14/server-side?kind={ride_id}")

    assert unfiltered.status_code == 200
    assert filtered.status_code == 200
    # The centre only clusters once the train ride supplies its fourth
    # neighbour, so filtering it away drops both counters.
    assert "You have 6 explored tiles" in unfiltered.text
    assert "There are 1 cluster tiles" in unfiltered.text
    assert "You have 4 explored tiles" in filtered.text
    assert "There are 0 cluster tiles" in filtered.text


def test_filtered_cluster_state_is_computed_once_per_filter(app, monkeypatch) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()
        _add_activity_tiles(1, ride, _PLUS_VISITED + [(1, 0)], dt.datetime(2026, 1, 1))

        calls = []
        original = filtered_module._compute_filtered_cluster_state

        def counting(zoom, activity_ids):
            calls.append(zoom)
            return original(zoom, activity_ids)

        monkeypatch.setattr(
            filtered_module, "_compute_filtered_cluster_state", counting
        )

        first = get_filtered_cluster_state(14, frozenset({1}))
        # A second worker process would start with an empty in-process cache but
        # must still find the stored row.
        filtered_module._process_cache.clear()
        second = get_filtered_cluster_state(14, frozenset({1}))

        assert calls == [14]
        assert first.membership == second.membership
        assert first.max_square_size == second.max_square_size

        # New activity tiles change the generation, so the row is recomputed.
        _add_activity_tiles(2, ride, [(9, 9)], dt.datetime(2026, 1, 2))
        filtered_module._process_cache.clear()
        get_filtered_cluster_state(14, frozenset({1}))
        assert calls == [14, 14]


def test_storing_a_filtered_state_tolerates_a_concurrent_writer(app) -> None:
    """A worker that loses the insert race must not raise."""
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()
        _add_activity_tiles(1, ride, _PLUS_VISITED, dt.datetime(2026, 1, 1))

        state = get_filtered_cluster_state(14, frozenset({1}))
        query_hash = filtered_module._query_hash(frozenset({1}))
        generation = filtered_module._activity_tile_generation()

        # Simulate the other worker having inserted the row already by writing
        # it twice; the second call must be a no-op rather than an error.
        filtered_module._store_filtered_cluster_state(query_hash, 14, generation, state)
        filtered_module._store_filtered_cluster_state(query_hash, 14, generation, state)

        assert (
            DB.session.query(FilteredClusterCache)
            .filter(FilteredClusterCache.query_hash == query_hash)
            .count()
            == 1
        )


def test_only_one_worker_claims_a_cluster_history_rebuild(app) -> None:
    """A second worker must not join a rebuild that is already running."""
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)
        DB.session.add(ClusterHistoryStatus(zoom=14, stale=True))
        DB.session.commit()

        assert _claim_cluster_history_rebuild(14) is True
        assert _claim_cluster_history_rebuild(14) is False

        # A claim from a crashed worker is taken over after the timeout.
        status = DB.session.get(ClusterHistoryStatus, 14)
        status.rebuilding_since = (
            dt.datetime.now() - CLUSTER_HISTORY_CLAIM_TIMEOUT - dt.timedelta(minutes=1)
        )
        DB.session.commit()
        assert _claim_cluster_history_rebuild(14) is True


def test_rebuild_if_stale_releases_the_claim(app) -> None:
    with app.app_context():
        _add_tile_visits(_MIXED_TILES)

        assert rebuild_cluster_history_if_stale(14) is True
        status = DB.session.get(ClusterHistoryStatus, 14)
        assert status.rebuilding_since is None
        assert not status.stale


def test_filtered_cluster_cache_cleanup(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()
        _add_activity_tiles(1, ride, _PLUS_VISITED, dt.datetime(2026, 1, 1))

        get_filtered_cluster_state(14, frozenset({1}))
        count, size = get_filtered_cluster_cache_stats()
        assert count == 1
        assert size > 0

        # A recent entry survives the stale cleanup.
        assert (
            delete_stale_filtered_cluster_cache(
                dt.datetime.now() - dt.timedelta(days=182)
            )
            == 0
        )
        assert get_filtered_cluster_cache_stats()[0] == 1

        # New activity tiles make the stored generation outdated.
        _add_activity_tiles(2, ride, [(20, 20)], dt.datetime(2026, 1, 2))
        assert delete_outdated_filtered_cluster_cache() == 1
        assert get_filtered_cluster_cache_stats()[0] == 0


def test_filtered_cluster_cache_stale_cleanup_drops_old_entries(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()
        _add_activity_tiles(1, ride, _PLUS_VISITED, dt.datetime(2026, 1, 1))
        get_filtered_cluster_state(14, frozenset({1}))

        row = DB.session.scalar(sa.select(FilteredClusterCache))
        row.last_used = dt.datetime.now() - dt.timedelta(days=200)
        DB.session.commit()

        dropped = delete_stale_filtered_cluster_cache(
            dt.datetime.now() - dt.timedelta(days=182)
        )
        assert dropped == 1
        assert get_filtered_cluster_cache_stats() == (0, 0)


def test_evolution_series_end_at_the_current_state_with_inaccessible_tiles(
    app,
) -> None:
    """The history plots must agree with the headline numbers. (GH-513)"""
    with app.app_context():
        _add_tile_visits(
            [(x, y) for x in range(3) for y in range(3) if (x, y) != (1, 1)]
        )
        DB.session.add(InaccessibleTile(zoom=14, tile_x=1, tile_y=1))
        DB.session.commit()
        _enable_counting_inaccessible()

        rebuild_cluster_history(14)

        covered = get_covered_tiles(14)
        assert (
            get_square_history_df(14)["max_square_size"].iloc[-1]
            == (compute_max_square(covered)[2])
        )
        assert get_cluster_size_history_df(14)["max_cluster_size"].iloc[-1] == (
            compute_current_cluster_state(covered).max_cluster_size
        )


def test_evolution_series_record_a_cluster_that_inaccessible_tiles_create(
    app,
) -> None:
    """A cluster that only the seeded tiles complete still needs a point."""
    with app.app_context():
        _add_tile_visits(_PLUS_VISITED)
        DB.session.add(
            InaccessibleTile(zoom=14, tile_x=_LAKE_TILE[0], tile_y=_LAKE_TILE[1])
        )
        DB.session.commit()
        _enable_counting_inaccessible()

        rebuild_cluster_history(14)

        assert get_cluster_size_history_df(14)["max_cluster_size"].iloc[-1] == 1
        assert get_square_history_df(14)["max_square_size"].iloc[-1] == 1


def test_deleting_an_activity_repairs_the_tile_visits_incrementally(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()

        _add_activity_tiles(1, ride, [(0, 0), (1, 0)], dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, ride, [(1, 0), (2, 0)], dt.datetime(2026, 1, 2))
        rebuild_tile_visits_from_activity_tiles()

        DB.session.delete(DB.session.get(Activity, 2))
        DB.session.commit()
        remove_activity_from_tile_state(2)

        assert get_visited_tiles(14) == {(0, 0), (1, 0)}
        shared = DB.session.scalar(
            sa.select(TileVisit).where(
                TileVisit.zoom == 14, TileVisit.tile_x == 1, TileVisit.tile_y == 0
            )
        )
        assert shared.visit_count == 1
        assert shared.first_activity_id == 1
        assert shared.last_activity_id == 1
        # The state is consistent, so the next scan does not wipe and rebuild it.
        assert _consistency_check()


def test_deleting_a_repeat_visitor_leaves_the_cluster_history_alone(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()

        _add_activity_tiles(1, ride, [(0, 0), (1, 0)], dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, ride, [(0, 0), (1, 0)], dt.datetime(2026, 1, 2))
        rebuild_tile_visits_from_activity_tiles()
        rebuild_cluster_history(14)
        assert not is_cluster_history_stale(14)

        DB.session.delete(DB.session.get(Activity, 2))
        DB.session.commit()
        remove_activity_from_tile_state(2)

        # Nothing was first visited by that activity, so the history still holds.
        assert not is_cluster_history_stale(14)
        assert get_visited_tiles(14) == {(0, 0), (1, 0)}


def test_deleting_the_first_visitor_marks_the_cluster_history_stale(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()

        _add_activity_tiles(1, ride, [(0, 0)], dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, ride, [(0, 0)], dt.datetime(2026, 1, 2))
        rebuild_tile_visits_from_activity_tiles()
        rebuild_cluster_history(14)

        DB.session.delete(DB.session.get(Activity, 1))
        DB.session.commit()
        remove_activity_from_tile_state(1)

        assert is_cluster_history_stale(14)
        visit = DB.session.scalar(sa.select(TileVisit).where(TileVisit.zoom == 14))
        assert visit.first_activity_id == 2


def test_shifting_a_start_reorders_first_visits_without_reprocessing(app) -> None:
    with app.app_context():
        ride = Kind(name="Ride")
        DB.session.add(ride)
        DB.session.commit()

        _add_activity_tiles(1, ride, [(0, 0)], dt.datetime(2026, 1, 1))
        _add_activity_tiles(2, ride, [(0, 0)], dt.datetime(2026, 1, 2))
        rebuild_tile_visits_from_activity_tiles()
        assert get_tile_history_df(14)["activity_id"].tolist() == [1]

        shift = dt.timedelta(days=-3)
        activity = DB.session.get(Activity, 2)
        activity.start += shift
        DB.session.commit()
        refresh_tile_visits_for_activity(2, time_shift=shift)

        visit = DB.session.scalar(sa.select(TileVisit).where(TileVisit.zoom == 14))
        assert visit.first_activity_id == 2
        assert visit.first_time == dt.datetime(2025, 12, 30)
        assert visit.visit_count == 2
        # The tile membership is untouched, only its timestamps moved.
        assert get_activity_ids_in_tile(14, 0, 0) == {1, 2}
        assert DB.session.scalar(
            sa.select(ActivityTile.time).where(ActivityTile.activity_id == 2)
        ) == dt.datetime(2025, 12, 30)
