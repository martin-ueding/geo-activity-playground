import datetime as dt
import pickle
import time
from types import SimpleNamespace

import pandas as pd
import sqlalchemy as sa

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    ClusterHistoryCheckpoint,
    ClusterHistoryEvent,
    TileVisit,
)
from geo_activity_playground.explorer.tile_visits import (
    CLUSTER_CHECKPOINT_INTERVAL,
    TileEvolutionState,
    TileVisitAccessor,
    _compute_cluster_evolution,
    _process_activity,
    _tiles_from_points,
    get_cluster_tile_activations_df,
    get_cluster_tile_diff_for_activity,
    get_cluster_tiles_at_cutoff,
    get_tile_history_df,
    get_tile_visits,
    invalidate_tile_visits_cache,
    make_tile_state,
    rebuild_cluster_history_for_zoom,
    remove_activity_from_tile_state,
)
from geo_activity_playground.webui.blueprints.heatmap_blueprint import _get_counts


def test_accessor_removes_persisted_tile_visits_key(app) -> None:
    with app.app_context():
        state_path = TileVisitAccessor.PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(
            pickle.dumps(
                {
                    "tile_visits": {14: {(1, 2): {"visit_count": 1}}},
                    "activities_per_tile": {},
                    "evolution_state": {},
                    "version": 3,
                }
            )
        )

        accessor = TileVisitAccessor()
        assert "tile_visits" not in accessor.tile_state

        persisted = pickle.loads(state_path.read_bytes())
        assert "tile_visits" not in persisted


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

        invalidate_tile_visits_cache()
        visits = get_tile_visits(14)
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

        invalidate_tile_visits_cache()
        visits = get_tile_visits(14)
        assert visits[(8, 9)]["first_time"] == pd.Timestamp("2026-01-01T10:00:00")
        assert visits[(8, 9)]["last_time"] == pd.Timestamp("2026-01-01T10:00:00")


def test_remove_activity_from_tile_state_removes_all_references() -> None:
    tile_state = make_tile_state()
    tile_state["activities_per_tile"][17][(1, 2)] = {1, 2}
    tile_state["activities_per_tile"][17][(2, 3)] = {2}
    tile_state["activities_per_tile"][18][(4, 5)] = {2, 3}

    removed = remove_activity_from_tile_state(tile_state, 2)

    assert removed == 3
    assert tile_state["activities_per_tile"][17][(1, 2)] == {1}
    assert (2, 3) not in tile_state["activities_per_tile"][17]
    assert tile_state["activities_per_tile"][18][(4, 5)] == {3}


def test_heatmap_counts_skip_deleted_activity_ids(app) -> None:
    class Repository:
        def get_time_series(self, activity_id: int) -> pd.DataFrame:
            if activity_id == 2:
                raise ValueError("Cannot find activity 2 in DB.session.")
            return pd.DataFrame({"x": [0.5], "y": [0.5], "segment_id": [0]})

    activities_per_tile = {17: {(1, 2): {1, 2}}}
    _ = _get_counts(1, 2, 17, {}, Repository(), activities_per_tile)
    assert activities_per_tile[17][(1, 2)] == {1, 2}


def test_process_activity_updates_first_and_last_fields_in_db(app) -> None:
    with app.app_context():
        DB.session.add_all([Activity(id=1, name="Older"), Activity(id=2, name="Newer")])
        DB.session.commit()

        class Repository:
            def __init__(self) -> None:
                self.activities = {
                    1: SimpleNamespace(
                        id=1,
                        kind=SimpleNamespace(consider_for_achievements=True),
                    ),
                    2: SimpleNamespace(
                        id=2,
                        kind=SimpleNamespace(consider_for_achievements=True),
                    ),
                }
                self.series = {
                    1: pd.DataFrame(
                        {
                            "time": [pd.Timestamp("2024-01-01T10:00:00Z")],
                            "x": [0.25],
                            "y": [0.25],
                            "segment_id": [0],
                        }
                    ),
                    2: pd.DataFrame(
                        {
                            "time": [pd.Timestamp("2024-01-02T10:00:00Z")],
                            "x": [0.25],
                            "y": [0.25],
                            "segment_id": [0],
                        }
                    ),
                }

            def get_activity_by_id(self, activity_id: int):
                return self.activities[activity_id]

            def get_time_series(self, activity_id: int) -> pd.DataFrame:
                return self.series[activity_id]

        repository = Repository()
        state = make_tile_state()
        _process_activity(repository, state, 2)
        _process_activity(repository, state, 1)

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
        DB.session.add(Activity(id=1, name="Mixed Time Activity"))
        DB.session.commit()

        class Repository:
            def __init__(self) -> None:
                self.activity = SimpleNamespace(
                    id=1,
                    kind=SimpleNamespace(consider_for_achievements=True),
                )
                self.series = pd.DataFrame(
                    {
                        "time": [pd.NaT, pd.Timestamp("2024-01-01T10:00:00Z")],
                        "x": [0.25, 0.25],
                        "y": [0.25, 0.25],
                        "segment_id": [0, 0],
                    }
                )

            def get_activity_by_id(self, activity_id: int):
                assert activity_id == 1
                return self.activity

            def get_time_series(self, activity_id: int) -> pd.DataFrame:
                assert activity_id == 1
                return self.series

        state = make_tile_state()
        _process_activity(Repository(), state, 1)

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
        DB.session.add_all(
            [
                Activity(
                    id=1, name="No Track Times", start=dt.datetime(2024, 1, 1, 9, 0, 0)
                ),
                Activity(
                    id=2, name="Later Visit", start=dt.datetime(2024, 1, 2, 9, 0, 0)
                ),
            ]
        )
        DB.session.commit()

        class Repository:
            def __init__(self) -> None:
                self.activities = {
                    1: SimpleNamespace(
                        id=1,
                        start=dt.datetime(2024, 1, 1, 9, 0, 0),
                        start_utc=dt.datetime(2024, 1, 1, 9, 0, 0, tzinfo=dt.UTC),
                        kind=SimpleNamespace(consider_for_achievements=True),
                    ),
                    2: SimpleNamespace(
                        id=2,
                        start=dt.datetime(2024, 1, 2, 9, 0, 0),
                        start_utc=dt.datetime(2024, 1, 2, 9, 0, 0, tzinfo=dt.UTC),
                        kind=SimpleNamespace(consider_for_achievements=True),
                    ),
                }
                self.series = {
                    1: pd.DataFrame(
                        {
                            "time": [pd.NaT],
                            "x": [0.25],
                            "y": [0.25],
                            "segment_id": [0],
                        }
                    ),
                    2: pd.DataFrame(
                        {
                            "time": [pd.Timestamp("2024-01-02T09:00:00Z")],
                            "x": [0.25],
                            "y": [0.25],
                            "segment_id": [0],
                        }
                    ),
                }

            def get_activity_by_id(self, activity_id: int):
                return self.activities[activity_id]

            def get_time_series(self, activity_id: int) -> pd.DataFrame:
                return self.series[activity_id]

        repository = Repository()
        state = make_tile_state()
        _process_activity(repository, state, 1)
        _process_activity(repository, state, 2)

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
        repository = ActivityRepository()
        assert repository.get_activity_ids() == [1, 2]

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


def test_cluster_history_projection_and_checkpoints(app) -> None:
    with app.app_context():
        activity = Activity(id=1, name="Ride")
        DB.session.add(activity)
        for i in range(CLUSTER_CHECKPOINT_INTERVAL + 5):
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
        checkpoint_indices = [
            row.event_index
            for row in DB.session.scalars(
                sa.select(ClusterHistoryCheckpoint)
                .where(ClusterHistoryCheckpoint.zoom == 14)
                .order_by(ClusterHistoryCheckpoint.event_index)
            ).all()
        ]
        assert checkpoint_indices[-1] == len(history)
        assert CLUSTER_CHECKPOINT_INTERVAL in checkpoint_indices


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
        added, removed = get_cluster_tile_diff_for_activity(14, 2)

        assert (0, 0) not in before
        assert (0, 0) in after
        assert added == {(0, 0)}
        assert removed == set()


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
