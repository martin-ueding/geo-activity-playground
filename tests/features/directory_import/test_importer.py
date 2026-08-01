import pathlib
import shutil

import sqlalchemy

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.core.import_exclusion import (
    ImportExclusion,
    record_exclusion,
)
from geo_activity_playground.features.directory_import.importer import (
    get_metadata_from_path,
    import_from_directory,
)


def _scan() -> None:
    accessor = ConfigAccessor()
    import_from_directory(
        ActivityRepository(),
        accessor.activity_import(),
        accessor.ui(),
        source="directory",
    )


def test_deleted_activity_is_not_imported_again(
    app_context, testdata_dir: pathlib.Path
) -> None:
    path = pathlib.Path("Activities/berlin.gpx")
    shutil.copy(
        testdata_dir / "Local Files" / "Activities" / "Berlin (0,9 km).gpx", path
    )

    _scan()
    activity = DB.session.scalar(sqlalchemy.select(Activity))
    assert activity is not None
    upstream_id = activity.upstream_id

    # Deleting an activity records an exclusion, as the delete route does.
    record_exclusion("directory", upstream_id, "deleted_by_user", path=activity.path)
    DB.session.delete(activity)
    DB.session.commit()

    _scan()
    assert DB.session.scalar(sqlalchemy.select(Activity)) is None

    # Renaming the file must not resurrect it either, since the key is the content.
    path.rename("Activities/berlin-renamed.gpx")
    _scan()
    assert DB.session.scalar(sqlalchemy.select(Activity)) is None

    # Dropping the exclusion brings the activity back.
    DB.session.execute(sqlalchemy.delete(ImportExclusion))
    DB.session.commit()
    _scan()
    assert DB.session.scalar(sqlalchemy.select(Activity)) is not None


def test_broken_file_is_recorded_and_skipped_until_changed(app_context) -> None:
    path = pathlib.Path("Activities/broken.xyz")
    path.write_text("not a real activity file")

    accessor = ConfigAccessor()
    repository = ActivityRepository()

    import_from_directory(
        repository, accessor.activity_import(), accessor.ui(), source="directory"
    )

    broken = DB.session.scalar(sqlalchemy.select(ImportExclusion))
    assert broken is not None
    assert broken.source == "directory"
    assert broken.path == str(path)
    assert broken.reason == "parse_error"
    first_attempt = broken.last_attempt

    # A second scan of the unchanged file must not touch the record.
    import_from_directory(
        repository, accessor.activity_import(), accessor.ui(), source="directory"
    )
    DB.session.expire_all()
    broken_again = DB.session.scalar(sqlalchemy.select(ImportExclusion))
    assert broken_again is not None
    assert broken_again.last_attempt == first_attempt

    # Once the file's content changes, it is retried and the record refreshed.
    path.write_text("still broken, but different content this time")
    import_from_directory(
        repository, accessor.activity_import(), accessor.ui(), source="directory"
    )
    DB.session.expire_all()
    broken_third = DB.session.scalars(sqlalchemy.select(ImportExclusion)).all()
    assert len(broken_third) == 1
    assert broken_third[0].last_attempt != first_attempt


def test_get_metadata_from_path() -> None:
    expected = {
        "kind": "Radfahrt",
        "equipment": "Bike 2019",
        "name": "Foo-Bar to Baz24",
    }
    actual = get_metadata_from_path(
        pathlib.Path(
            "Activities/Radfahrt/Bike 2019/Foo-Bar to Baz24/2024-03-03-17-42-10 Something something.fit"
        ),
        [
            r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/(?P<name>[^/]+)/",
            r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ ]+(?P<name>[^/\.]+)(?:\.\w+)+$",
            r"(?P<kind>[^/]+)/[-\d_ ]+(?P<name>[^/\.]+)(?:\.\w+)+$",
        ],
    )
    assert actual == expected
