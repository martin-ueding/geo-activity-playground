import datetime
import io
import json
import zipfile
from types import SimpleNamespace

import sqlalchemy

from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    ClusterHistoryCheckpoint,
    ClusterHistoryEvent,
    Equipment,
    ExplorerTileBookmark,
    HeatmapTileCache,
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
from geo_activity_playground.importers import strava_api


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
        heatmap_cache = HeatmapTileCache(
            zoom=14,
            tile_x=1,
            tile_y=2,
            search_query_id=None,
            counts=b"not-used",
            included_activity_ids=[1],
            num_activities=1,
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
                heatmap_cache,
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
            ClusterHistoryEvent,
            ClusterHistoryCheckpoint,
            Segment,
            SegmentMatch,
            SegmentCheck,
            ExplorerTileBookmark,
            SquarePlannerBookmark,
            PlotSpec,
            StoredSearchQuery,
            HeatmapTileCache,
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


def test_reset_heatmap_cache_clears_db_table(client, app):
    with app.app_context():
        cache = HeatmapTileCache(
            zoom=14,
            tile_x=1,
            tile_y=2,
            search_query_id=None,
            counts=b"payload",
            included_activity_ids=[],
            num_activities=0,
            last_used=datetime.datetime(2024, 1, 1),
        )
        DB.session.add(cache)
        DB.session.commit()

    response = client.post(
        "/settings/maintenance", data={"action": "reset_heatmap_cache"}
    )
    assert response.status_code == 302

    with app.app_context():
        assert (
            DB.session.scalar(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(HeatmapTileCache)
            )
            == 0
        )


def test_cleanup_heatmap_cache_stale_removes_old_and_never_used_entries(client, app):
    now = datetime.datetime.now()
    with app.app_context():
        stale = HeatmapTileCache(
            zoom=14,
            tile_x=1,
            tile_y=1,
            search_query_id=None,
            counts=b"a",
            included_activity_ids=[],
            num_activities=0,
            last_used=now - datetime.timedelta(days=400),
        )
        never_used = HeatmapTileCache(
            zoom=14,
            tile_x=1,
            tile_y=2,
            search_query_id=None,
            counts=b"b",
            included_activity_ids=[],
            num_activities=0,
            last_used=None,
        )
        recent = HeatmapTileCache(
            zoom=14,
            tile_x=1,
            tile_y=3,
            search_query_id=None,
            counts=b"c",
            included_activity_ids=[],
            num_activities=0,
            last_used=now - datetime.timedelta(days=10),
        )
        DB.session.add_all([stale, never_used, recent])
        DB.session.commit()

    response = client.post(
        "/settings/maintenance", data={"action": "cleanup_heatmap_cache_stale"}
    )
    assert response.status_code == 302

    with app.app_context():
        remaining = DB.session.scalars(sqlalchemy.select(HeatmapTileCache)).all()
        assert len(remaining) == 1
        assert remaining[0].tile_y == 3


class _FakeStravaClient:
    def __init__(self, pages):
        self._pages = pages
        self.calls: list[tuple[int, int]] = []

    def get_activities(self, page: int, per_page: int):
        self.calls.append((page, per_page))
        return self._pages.get(page, [])


def test_refresh_strava_activity_names_updates_matching_records(
    client, app, monkeypatch
):
    with app.app_context():
        equipment = Equipment(name="Road Bike")
        kind = Kind(
            name="Ride", consider_for_achievements=True, default_equipment=equipment
        )
        activity = Activity(
            name="Morning Ride",
            equipment=equipment,
            kind=kind,
            upstream_id="11",
            time_series_uuid="test-uuid",
        )
        DB.session.add_all([equipment, kind, activity])
        DB.session.commit()

    first_page = [SimpleNamespace(id=11, name="Updated from Strava")] + [
        SimpleNamespace(id=1_000 + i, name=f"Irrelevant {i}") for i in range(199)
    ]
    fake_client = _FakeStravaClient(pages={1: first_page, 2: []})

    def client_factory(*, access_token):
        assert access_token == "token"
        return fake_client

    monkeypatch.setattr(strava_api, "Client", client_factory)
    monkeypatch.setattr(strava_api, "get_current_access_token", lambda _: "token")

    response = client.post(
        "/settings/maintenance", data={"action": "refresh_strava_activity_names"}
    )

    assert response.status_code == 302
    assert fake_client.calls == [(1, 200), (2, 200)]

    with app.app_context():
        refreshed = DB.session.scalar(
            sqlalchemy.select(Activity).where(Activity.upstream_id == "11")
        )
        assert refreshed is not None
        assert refreshed.name == "Updated from Strava"


def test_refresh_strava_activity_names_is_noop_if_names_match(client, app, monkeypatch):
    with app.app_context():
        equipment = Equipment(name="Road Bike")
        kind = Kind(
            name="Ride", consider_for_achievements=True, default_equipment=equipment
        )
        activity = Activity(
            name="Already Synced",
            equipment=equipment,
            kind=kind,
            upstream_id="11",
            time_series_uuid="test-uuid",
        )
        DB.session.add_all([equipment, kind, activity])
        DB.session.commit()

    fake_client = _FakeStravaClient(
        pages={1: [SimpleNamespace(id=11, name="Already Synced")], 2: []}
    )

    def client_factory(*, access_token):
        assert access_token == "token"
        return fake_client

    monkeypatch.setattr(strava_api, "Client", client_factory)
    monkeypatch.setattr(strava_api, "get_current_access_token", lambda _: "token")

    response = client.post(
        "/settings/maintenance", data={"action": "refresh_strava_activity_names"}
    )
    assert response.status_code == 302

    with app.app_context():
        refreshed = DB.session.scalar(
            sqlalchemy.select(Activity).where(Activity.upstream_id == "11")
        )
        assert refreshed is not None
        assert refreshed.name == "Already Synced"


def test_strava_checkout_upload_replaces_existing_checkout(client, tmp_path):
    checkout_dir = tmp_path / "Strava Export"
    checkout_dir.mkdir(parents=True)
    (checkout_dir / "old.txt").write_text("old", encoding="utf-8")

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, mode="w") as archive:
        archive.writestr("activities.csv", "Activity ID,Filename\n1,activities/a.fit\n")
        archive.writestr("activities/a.fit", "dummy-fit")
    archive_bytes.seek(0)

    response = client.post(
        "/settings/strava-upload",
        data={"strava_checkout_zip": (archive_bytes, "strava-export.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert not (checkout_dir / "old.txt").exists()
    assert (checkout_dir / "activities.csv").exists()
    assert (checkout_dir / "activities" / "a.fit").read_text(
        encoding="utf-8"
    ) == "dummy-fit"
