import datetime as dt

import sqlalchemy

from geo_activity_playground.core.config import Config
from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Segment,
    SegmentCheck,
    SegmentMatch,
)
from geo_activity_playground.core.segments import rematch_segment, tiles_for_segment


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
