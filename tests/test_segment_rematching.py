import datetime as dt

import sqlalchemy

from geo_activity_playground.core.config import Config
from geo_activity_playground.core.coordinates import get_distance
from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Segment,
    SegmentCheck,
    SegmentMatch,
)
from geo_activity_playground.core.segments import (
    rematch_segment,
    tiles_for_segment,
    try_match_segment_activity,
)


def test_rematch_segment_deletes_checks_and_matches_before_matching(app) -> None:
    with app.app_context():
        segment = Segment(name="Test Segment")
        segment.coordinates = [[50.0, 7.0], [50.001, 7.001]]
        activity = Activity(name="Test Activity")
        DB.session.add_all([segment, activity])
        DB.session.commit()

        DB.session.add(SegmentCheck(segment=segment, activity=activity))
        DB.session.add(
            SegmentMatch(
                segment=segment,
                activity=activity,
                entry_index=0,
                exit_index=1,
                entry_time=dt.datetime(2025, 1, 1, 10, 0, 0),
                exit_time=dt.datetime(2025, 1, 1, 10, 1, 0),
                duration=dt.timedelta(minutes=1),
                distance_km=0.4,
            )
        )
        DB.session.commit()

        segment_tiles = tiles_for_segment(segment, 17)
        empty_candidates = {tile: set() for tile in segment_tiles}
        deleted_matches, deleted_checks = rematch_segment(
            segment, empty_candidates, Config()
        )

        assert deleted_matches == 1
        assert deleted_checks == 1
        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(SegmentMatch.id)))
            == 0
        )
        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(SegmentCheck.id)))
            == 0
        )


def test_segment_length_km_uses_lat_lon_coordinate_order() -> None:
    segment = Segment(name="Order Test")
    segment.coordinates = [[50.0, 7.0], [50.0, 7.1]]

    expected_km = get_distance(50.0, 7.0, 50.0, 7.1) / 1000
    wrong_order_km = get_distance(7.0, 50.0, 7.1, 50.0) / 1000

    assert segment.length_km == expected_km
    assert segment.length_km != wrong_order_km


def test_try_match_segment_activity_skips_activities_without_start_time(
    app, monkeypatch
) -> None:
    with app.app_context():
        segment = Segment(name="Test Segment")
        segment.coordinates = [[50.0, 7.0], [50.001, 7.001]]
        activity = Activity(name="Untimed Activity", start=None)
        DB.session.add_all([segment, activity])
        DB.session.commit()

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError(
                "segment_track_distance must not run for untimed activities"
            )

        monkeypatch.setattr(
            "geo_activity_playground.core.segments.segment_track_distance",
            fail_if_called,
        )

        try_match_segment_activity(segment, activity, Config())

        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(SegmentCheck.id)))
            == 0
        )
        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(SegmentMatch.id)))
            == 0
        )
