import uuid
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from flask import Flask

from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.features.streets.matching import (
    _collapse_into_runs,
    compute_street_visits_new,
    get_new_street_length_m_for_activity,
    match_activity_to_streets,
)
from geo_activity_playground.features.streets.model import (
    ActivityStreetChunkRun,
    StreetChunkVisit,
)
from geo_activity_playground.features.streets.osm_fetch import _store_ways


def test_collapse_into_runs_merges_consecutive_chunks_on_same_way() -> None:
    chunks = [(1, 0), (1, 1), (1, 2), (1, 3)]

    runs = _collapse_into_runs(chunks)

    assert runs == [(1, 0, 3)]


def test_collapse_into_runs_splits_on_way_change() -> None:
    chunks = [(1, 0), (1, 1), (2, 0), (2, 1)]

    runs = _collapse_into_runs(chunks)

    assert runs == [(1, 0, 1), (2, 0, 1)]


def test_collapse_into_runs_splits_on_gap_within_same_way() -> None:
    chunks = [(1, 0), (1, 1), (1, 5), (1, 6)]

    runs = _collapse_into_runs(chunks)

    assert runs == [(1, 0, 1), (1, 5, 6)]


def test_collapse_into_runs_handles_reversed_traversal() -> None:
    chunks = [(1, 3), (1, 2), (1, 1), (1, 0)]

    runs = _collapse_into_runs(chunks)

    assert runs == [(1, 0, 3)]


def test_collapse_into_runs_of_empty_input() -> None:
    assert _collapse_into_runs([]) == []


def test_collapse_into_runs_revisiting_same_way_later_stays_separate() -> None:
    chunks = [(1, 0), (1, 1), (2, 0), (1, 5), (1, 6)]

    runs = _collapse_into_runs(chunks)

    assert runs == [(1, 0, 1), (2, 0, 0), (1, 5, 6)]


def _make_activity_along_street(app: Flask) -> tuple[int, float]:
    """Store a straight synthetic street (A-B-C, long enough to need several
    ~20 m chunks) and an Activity whose track follows it closely, without any
    network access. Returns the activity id and the street's total length."""
    node_a = (52.0, 13.0)
    node_b = (52.0, 13.0006)
    node_c = (52.0, 13.0012)
    nodes = {1: node_a, 2: node_b, 3: node_c}
    ways = [
        {
            "osm_id": 500,
            "highway": "residential",
            "name": "Teststraße",
            "node_ids": [1, 2, 3],
        }
    ]
    _store_ways(nodes, ways)
    DB.session.commit()

    lats = np.linspace(node_a[0], node_c[0], 40)
    lons = np.linspace(node_a[1], node_c[1], 40)
    time_series = pd.DataFrame({"latitude": lats, "longitude": lons})

    activity = Activity(
        id=1,
        name="Along the test street",
        start=pd.Timestamp("2026-01-01T10:00:00"),
        time_series_uuid=str(uuid.uuid4()),
    )
    DB.session.add(activity)
    DB.session.flush()
    activity.replace_time_series(time_series)
    DB.session.commit()

    from geo_activity_playground.core.coordinates import get_distance

    total_length = get_distance(*node_a, *node_b) + get_distance(*node_b, *node_c)
    return activity.id, total_length


def test_match_activity_to_streets_end_to_end(app_context: None, app: Flask) -> None:
    activity_id, total_length = _make_activity_along_street(app)

    with patch(
        "geo_activity_playground.features.streets.matching.ensure_streets_for_path"
    ):
        match_activity_to_streets(activity_id)

    runs = DB.session.query(ActivityStreetChunkRun).all()
    assert len(runs) == 1
    assert runs[0].activity_id == activity_id

    visits = DB.session.query(StreetChunkVisit).all()
    assert len(visits) > 1
    assert all(visit.first_activity_id == activity_id for visit in visits)
    assert all(visit.visit_count == 1 for visit in visits)

    new_length = get_new_street_length_m_for_activity(activity_id)
    assert new_length == pytest.approx(total_length, rel=0.05)


def test_compute_street_visits_new_skips_already_processed_activities(
    app_context: None, app: Flask
) -> None:
    activity_id, _total_length = _make_activity_along_street(app)

    with patch(
        "geo_activity_playground.features.streets.matching.ensure_streets_for_path"
    ) as mocked_ensure:
        compute_street_visits_new()
        assert mocked_ensure.call_count == 1

        # A second run must not re-match the same activity.
        compute_street_visits_new()
        assert mocked_ensure.call_count == 1
