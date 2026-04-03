import datetime
import json

import sqlalchemy

from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Equipment,
    ExplorerTileBookmark,
    Kind,
    Photo,
    PlotSpec,
    Segment,
    SegmentCheck,
    SegmentMatch,
    SquarePlannerBookmark,
    StoredSearchQuery,
    Tag,
    TileVisit,
    activity_tag_association_table,
)


def test_wipe_local_state_truncates_user_tables_and_files(client, app, tmp_path):
    with app.app_context():
        equipment = Equipment(name="Road Bike")
        kind = Kind(
            name="Ride", consider_for_achievements=True, default_equipment=equipment
        )
        activity = Activity(
            name="Morning Ride",
            equipment=equipment,
            kind=kind,
            time_series_uuid="test-uuid",
        )
        tag = Tag(tag="commute")
        activity.tags.append(tag)
        segment = Segment(
            name="River Segment",
            coordinates_json="[[50.0, 7.0], [50.1, 7.1]]",
        )
        segment_match = SegmentMatch(
            segment=segment,
            activity=activity,
            entry_index=0,
            exit_index=1,
        )
        segment_check = SegmentCheck(segment=segment, activity=activity)
        photo = Photo(
            filename="Photos/test.jpg",
            time=datetime.datetime(2024, 1, 1),
            latitude=50.0,
            longitude=7.0,
            activity=activity,
        )
        tile_visit = TileVisit(
            zoom=14,
            tile_x=1,
            tile_y=2,
            first_activity=activity,
            last_activity=activity,
            visit_count=1,
        )
        explorer_bookmark = ExplorerTileBookmark(
            name="Home", zoom=14, tile_x=1, tile_y=2
        )
        square_bookmark = SquarePlannerBookmark(
            zoom=14,
            x=100,
            y=200,
            size=3,
            name="Square",
        )
        plot_spec = PlotSpec(
            name="My Plot",
            mark="point",
            x="start",
            y="distance_km",
            color="kind",
            shape="",
            size="",
            row="",
            opacity="",
            column="",
            facet="",
            group_by="",
        )
        stored_query = StoredSearchQuery(
            query_json=json.dumps({"name": "Morning Ride"}),
            is_favorite=False,
            last_used=datetime.datetime(2024, 1, 1),
        )

        DB.session.add_all(
            [
                equipment,
                kind,
                activity,
                tag,
                segment,
                segment_match,
                segment_check,
                photo,
                tile_visit,
                explorer_bookmark,
                square_bookmark,
                plot_spec,
                stored_query,
            ]
        )
        DB.session.commit()

    (tmp_path / "Cache" / "work-tracker-tile-state.pickle").write_bytes(b"tracker")
    (tmp_path / "Cache" / "strava-last-activity-date.json").write_text(
        '"2024-01-01T00:00:00Z"',
        encoding="utf-8",
    )
    (tmp_path / "Time Series" / "stale.parquet").write_text("stale", encoding="utf-8")
    (tmp_path / "Photos").mkdir()
    (tmp_path / "Photos" / "stale.jpg").write_text("stale", encoding="utf-8")
    (tmp_path / "Strava API").mkdir()
    (tmp_path / "Strava API" / "strava_tokens.json").write_text(
        '{"access":"token"}',
        encoding="utf-8",
    )

    response = client.post("/settings/maintenance", data={"action": "wipe_local_state"})
    assert response.status_code == 302

    with app.app_context():
        assert (
            DB.session.scalar(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(Equipment)
            )
            == 1
        )
        assert (
            DB.session.scalar(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(Kind)
            )
            == 1
        )

        for model in [
            Activity,
            Tag,
            Photo,
            TileVisit,
            Segment,
            SegmentMatch,
            SegmentCheck,
            ExplorerTileBookmark,
            SquarePlannerBookmark,
            PlotSpec,
            StoredSearchQuery,
        ]:
            assert (
                DB.session.scalar(
                    sqlalchemy.select(sqlalchemy.func.count()).select_from(model)
                )
                == 0
            )

        assert (
            DB.session.scalar(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(
                    activity_tag_association_table
                )
            )
            == 0
        )

    assert list((tmp_path / "Cache").iterdir()) == []
    assert list((tmp_path / "Time Series").iterdir()) == []
    assert list((tmp_path / "Photos").iterdir()) == []

    assert (tmp_path / "Strava API" / "strava_tokens.json").exists()
