import pathlib

import pandas as pd
import sqlalchemy

from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.core.import_exclusion import ImportExclusion


def _make_activity() -> Activity:
    activity = Activity(
        name="Morning Ride",
        time_series_uuid="test-uuid",
        path="Activities/morning-ride.gpx",
        upstream_id="deadbeef",
        source="directory",
    )
    DB.session.add(activity)
    DB.session.commit()
    pd.DataFrame({"time": [], "latitude": [], "longitude": []}).to_parquet(
        activity.time_series_path
    )
    return activity


def test_delete_records_exclusion_and_removes_time_series(client, app):
    with app.app_context():
        activity = _make_activity()
        activity_id = activity.id
        time_series_path = activity.time_series_path
        assert time_series_path.exists()

    response = client.post(f"/activity/delete/{activity_id}", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert DB.session.get(Activity, activity_id) is None
        assert not time_series_path.exists()

        exclusion = DB.session.scalar(sqlalchemy.select(ImportExclusion))
        assert exclusion is not None
        assert exclusion.source == "directory"
        assert exclusion.upstream_id == "deadbeef"
        assert exclusion.reason == "deleted_by_user"
        assert exclusion.path == "Activities/morning-ride.gpx"


def test_delete_is_not_reachable_by_get(client, app):
    with app.app_context():
        activity_id = _make_activity().id

    assert client.get(f"/activity/delete/{activity_id}").status_code == 405

    with app.app_context():
        assert DB.session.get(Activity, activity_id) is not None


def test_delete_leaves_the_source_file_untouched(client, app):
    source_file = pathlib.Path("Activities/morning-ride.gpx")
    with app.app_context():
        activity_id = _make_activity().id
        source_file.write_text("<gpx/>")

    client.post(f"/activity/delete/{activity_id}", follow_redirects=True)

    assert source_file.exists()


def test_reimport_removes_the_exclusion(client, app):
    with app.app_context():
        activity_id = _make_activity().id

    client.post(f"/activity/delete/{activity_id}", follow_redirects=True)

    with app.app_context():
        exclusion_id = DB.session.scalar(sqlalchemy.select(ImportExclusion)).id

    response = client.post(
        f"/settings/excluded-activities/reimport/{exclusion_id}", follow_redirects=True
    )
    assert response.status_code == 200

    with app.app_context():
        assert DB.session.scalar(sqlalchemy.select(ImportExclusion)) is None


def test_reimport_all_does_not_resurrect_deleted_activities(client, app):
    with app.app_context():
        activity_id = _make_activity().id

    client.post(f"/activity/delete/{activity_id}", follow_redirects=True)
    client.post("/settings/excluded-activities/reimport-all", follow_redirects=True)

    with app.app_context():
        exclusion = DB.session.scalar(sqlalchemy.select(ImportExclusion))
        assert exclusion is not None
        assert exclusion.reason == "deleted_by_user"
