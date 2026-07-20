import pathlib

import pytest
import sqlalchemy

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB
from ...webui.app import create_app
from .importer import get_metadata_from_path, import_from_directory
from .model import BrokenActivityFile


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Activities").mkdir()
    app = create_app(database_uri="sqlite:///:memory:", run_migrations=False)
    with app.app_context():
        yield


def test_broken_file_is_recorded_and_skipped_until_changed(app_context) -> None:
    path = pathlib.Path("Activities/broken.xyz")
    path.write_text("not a real activity file")

    accessor = ConfigAccessor()
    repository = ActivityRepository()

    import_from_directory(repository, accessor.activity_import(), accessor.ui())

    broken = DB.session.scalar(sqlalchemy.select(BrokenActivityFile))
    assert broken is not None
    assert broken.path == str(path)
    assert broken.reason == "parse_error"
    first_attempt = broken.last_attempt

    # A second scan of the unchanged file must not touch the record.
    import_from_directory(repository, accessor.activity_import(), accessor.ui())
    DB.session.expire_all()
    broken_again = DB.session.scalar(sqlalchemy.select(BrokenActivityFile))
    assert broken_again is not None
    assert broken_again.last_attempt == first_attempt

    # Once the file's content changes, it is retried and the record refreshed.
    path.write_text("still broken, but different content this time")
    import_from_directory(repository, accessor.activity_import(), accessor.ui())
    DB.session.expire_all()
    broken_third = DB.session.scalar(sqlalchemy.select(BrokenActivityFile))
    assert broken_third is not None
    assert broken_third.last_attempt != first_attempt


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
