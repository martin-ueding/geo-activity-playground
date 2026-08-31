import pathlib
import shutil

import sqlalchemy

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity, get_or_make_kind
from geo_activity_playground.core.scan import refresh_stale_ingests
from geo_activity_playground.features.directory_import.importer import (
    import_from_directory,
)

BERLIN = "Berlin (0,9 km).gpx"


def _import_one(testdata_dir: pathlib.Path) -> Activity:
    path = pathlib.Path("Activities/Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(testdata_dir / "Local Files" / "Activities" / BERLIN, path)
    accessor = ConfigAccessor()
    accessor.activity_import().metadata_extraction_regexes = [
        r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$"
    ]
    accessor.save()
    import_from_directory(accessor.activity_import(), source="directory")
    activity = DB.session.scalar(sqlalchemy.select(Activity))
    assert activity is not None
    return activity


def test_reimport_route_keeps_user_edits(client, app, testdata_dir: pathlib.Path):
    with app.app_context():
        activity = _import_one(testdata_dir)
        activity_id = activity.id
        activity.name_from_user = "Zum Markt"
        activity.kind_from_user = get_or_make_kind("Wanderung")
        DB.session.commit()
        # Something the re-import has to restore.
        activity.distance_km = None
        DB.session.commit()

    response = client.post(f"/activity/{activity_id}/reimport")
    assert response.status_code == 302

    with app.app_context():
        activity = DB.session.get(Activity, activity_id)
        assert activity is not None
        assert activity.distance_km is not None
        assert activity.name == "Zum Markt"
        assert activity.kind.name == "Wanderung"
        assert activity.name_from_path == "Zum Bahnhof"


def test_reimport_route_reports_missing_source_data(
    client, app, testdata_dir: pathlib.Path
):
    with app.app_context():
        activity = _import_one(testdata_dir)
        activity_id = activity.id
        pathlib.Path(activity.path).unlink()

    response = client.post(f"/activity/{activity_id}/reimport")
    assert response.status_code == 302
    with client.session_transaction() as session:
        categories = [category for category, _message in session["_flashes"]]
        messages = [message for _category, message in session["_flashes"]]
    assert categories == ["warning"]
    assert "source data is not available" in messages[0]


def test_reparse_covers_every_activity_regardless_of_stamp(
    app_context, testdata_dir: pathlib.Path
):
    activity = _import_one(testdata_dir)
    accessor = ConfigAccessor()

    # Nothing is stale, so the scan's own pass does nothing.
    assert refresh_stale_ingests(accessor) == (0, 0)

    activity.distance_km = None
    DB.session.commit()

    assert refresh_stale_ingests(accessor, force=True) == (1, 0)
    assert DB.session.get(Activity, activity.id).distance_km is not None
