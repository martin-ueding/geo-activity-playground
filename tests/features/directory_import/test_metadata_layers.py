import pathlib
import shutil

import sqlalchemy

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    get_or_make_kind,
    materialize_metadata,
)
from geo_activity_playground.features.activity.blueprint import apply_metadata
from geo_activity_playground.features.directory_import.importer import (
    import_from_directory,
)

REGEXES = [
    r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
    r"(?P<kind>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
]


def _place_activity(testdata_dir: pathlib.Path, relative: str) -> pathlib.Path:
    path = pathlib.Path("Activities") / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        testdata_dir / "Local Files" / "Activities" / "Berlin (0,9 km).gpx", path
    )
    return path


def _scan() -> Activity:
    accessor = ConfigAccessor()
    accessor.activity_import().metadata_extraction_regexes = REGEXES
    accessor.save()
    import_from_directory(accessor.activity_import(), source="directory")
    activity = DB.session.scalar(sqlalchemy.select(Activity))
    assert activity is not None
    return activity


def test_path_layer_is_stored_and_materialized(
    app_context, testdata_dir: pathlib.Path
) -> None:
    _place_activity(testdata_dir, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    activity = _scan()

    assert activity.kind_from_path == "Radfahrt"
    assert activity.equipment_from_path == "Rennrad"
    assert activity.name_from_path == "Zum Bahnhof"

    assert activity.kind.name == "Radfahrt"
    assert activity.equipment.name == "Rennrad"
    assert activity.name == "Zum Bahnhof"


def test_user_layer_wins_over_path_and_file(
    app_context, testdata_dir: pathlib.Path
) -> None:
    _place_activity(testdata_dir, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    activity = _scan()

    activity.kind_from_user = get_or_make_kind("Wanderung")
    activity.name_from_user = "Zum Markt"
    materialize_metadata(activity)

    assert activity.kind.name == "Wanderung"
    assert activity.name == "Zum Markt"
    # The lower layers still record what the source said.
    assert activity.kind_from_path == "Radfahrt"
    assert activity.name_from_path == "Zum Bahnhof"


def test_reimport_keeps_user_edits(app_context, testdata_dir: pathlib.Path) -> None:
    path = _place_activity(testdata_dir, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    activity = _scan()

    activity.name_from_user = "Zum Markt"
    activity.kind_from_user = get_or_make_kind("Wanderung")
    materialize_metadata(activity)
    DB.session.commit()

    # Re-importing the very same file refreshes the lower layers.
    upstream_id = activity.upstream_id
    DB.session.delete(activity)
    DB.session.commit()
    reimported = _scan()

    assert reimported.upstream_id == upstream_id
    assert reimported.name_from_path == "Zum Bahnhof"
    # A fresh import carries no user layer, so the path wins again.
    assert reimported.name == "Zum Bahnhof"

    # Carrying the user layer over is what a re-import button would do.
    reimported.name_from_user = "Zum Markt"
    materialize_metadata(reimported)
    assert reimported.name == "Zum Markt"

    assert path.exists()


def test_unchanged_form_value_does_not_pin_the_activity(
    app_context, testdata_dir: pathlib.Path
) -> None:
    _place_activity(testdata_dir, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    activity = _scan()

    apply_metadata(
        activity,
        name=activity.name,
        description=None,
        equipment_id=str(activity.equipment.id),
        kind_id=str(activity.kind.id),
        tag_ids=[],
    )

    assert activity.name_from_user is None
    assert activity.kind_from_user is None
    assert activity.equipment_from_user is None
    assert activity.name == "Zum Bahnhof"


def test_changed_form_value_is_recorded_as_an_override(
    app_context, testdata_dir: pathlib.Path
) -> None:
    _place_activity(testdata_dir, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    activity = _scan()
    wanderung = get_or_make_kind("Wanderung")
    DB.session.add(wanderung)
    DB.session.commit()

    apply_metadata(
        activity,
        name="Zum Markt",
        description=None,
        equipment_id=str(activity.equipment.id),
        kind_id=str(wanderung.id),
        tag_ids=[],
    )

    assert activity.name_from_user == "Zum Markt"
    assert activity.kind_from_user is not None
    assert activity.kind_from_user.name == "Wanderung"
    assert activity.equipment_from_user is None
    assert activity.name == "Zum Markt"
    assert activity.kind.name == "Wanderung"
