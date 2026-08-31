import pathlib
import shutil

import sqlalchemy

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity, get_or_make_kind
from geo_activity_playground.core.enrichment import enrichments
from geo_activity_playground.core.pipeline import (
    current_enrichment_versions,
    refresh_stale_enrichments,
)
from geo_activity_playground.features.directory_import.importer import (
    import_from_directory,
)

REGEXES = [
    r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
    r"(?P<kind>[^/]+)/[-\d_ .]+(?P<name>[^/\.]+)(?:\.\w+)+$",
]

BERLIN = "Berlin (0,9 km).gpx"


def _config() -> ConfigAccessor:
    accessor = ConfigAccessor()
    accessor.activity_import().metadata_extraction_regexes = REGEXES
    accessor.save()
    return accessor


def _place(testdata_dir: pathlib.Path, name: str, relative: str) -> pathlib.Path:
    path = pathlib.Path("Activities") / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(testdata_dir / "Local Files" / "Activities" / name, path)
    return path


def _shorten_gpx(source: pathlib.Path, target: pathlib.Path, drop: int) -> None:
    """Write a variant of a GPX file with the last few track points removed."""
    text = source.read_text()
    for _ in range(drop):
        end = text.rindex("</trkpt>")
        start = text.rindex("<trkpt", 0, end)
        text = text[:start] + text[end + len("</trkpt>") :]
    target.write_text(text)


def _scan() -> None:
    import_from_directory(_config().activity_import(), source="directory")


def _only_activity() -> Activity:
    activity = DB.session.scalar(sqlalchemy.select(Activity))
    assert activity is not None
    return activity


def test_moved_file_updates_path_and_path_layer(
    app_context, testdata_dir: pathlib.Path
) -> None:
    loose = _place(testdata_dir, BERLIN, "2024-01-02 Zum Bahnhof.gpx")
    _scan()
    activity = _only_activity()
    activity_id = activity.id
    assert activity.equipment_from_path is None

    # This is what the sorting script does: the same file, in a directory that
    # states the kind and the equipment.
    sorted_path = pathlib.Path("Activities/Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    sorted_path.parent.mkdir(parents=True, exist_ok=True)
    loose.rename(sorted_path)
    _scan()

    activity = _only_activity()
    assert activity.id == activity_id
    assert activity.path == str(sorted_path)
    assert activity.kind_from_path == "Radfahrt"
    assert activity.equipment_from_path == "Rennrad"
    assert activity.kind.name == "Radfahrt"
    assert activity.equipment.name == "Rennrad"


def test_a_copy_is_not_treated_as_a_move(
    app_context, testdata_dir: pathlib.Path
) -> None:
    original = _place(testdata_dir, BERLIN, "Radfahrt/Rennrad/2024-01-02 Erst.gpx")
    _scan()
    activity_id = _only_activity().id

    shutil.copy(original, "Activities/Radfahrt/Rennrad/2024-01-02 Zweit.gpx")
    _scan()

    activity = _only_activity()
    assert activity.id == activity_id
    # The original is still there, so the path must not follow the copy.
    assert activity.path == str(original)


def test_changed_file_keeps_the_activity_and_its_user_edits(
    app_context, testdata_dir: pathlib.Path
) -> None:
    path = _place(testdata_dir, BERLIN, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    _scan()
    activity = _only_activity()
    activity_id = activity.id
    first_hash = activity.upstream_id
    first_distance = activity.distance_km

    activity.name_from_user = "Zum Markt"
    activity.kind_from_user = get_or_make_kind("Wanderung")
    DB.session.commit()

    # Same path, different content.
    _shorten_gpx(testdata_dir / "Local Files" / "Activities" / BERLIN, path, 5)
    _scan()

    activity = _only_activity()
    assert activity.id == activity_id
    assert activity.upstream_id != first_hash
    assert activity.distance_km != first_distance
    # The user layer survived the content change.
    assert activity.name == "Zum Markt"
    assert activity.kind.name == "Wanderung"


def test_changed_file_resets_a_trim_of_a_different_length(
    app_context, testdata_dir: pathlib.Path
) -> None:
    path = _place(testdata_dir, BERLIN, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    _scan()
    activity = _only_activity()
    activity.index_begin = 2
    activity.index_end = 5
    DB.session.commit()

    _shorten_gpx(testdata_dir / "Local Files" / "Activities" / BERLIN, path, 5)
    _scan()

    activity = _only_activity()
    assert activity.index_begin is None
    assert activity.index_end is None


def test_a_lagging_enrichment_stamp_makes_the_step_run_again(
    app_context, testdata_dir: pathlib.Path
) -> None:
    _place(testdata_dir, BERLIN, "Radfahrt/Rennrad/2024-01-02 Zum Bahnhof.gpx")
    _scan()
    activity = _only_activity()
    assert activity.enrichment_versions == current_enrichment_versions()

    # An activity whose stamp lags behind is caught up, and one that is current is
    # left alone.
    assert refresh_stale_enrichments(_config().activity_import()) == 0

    activity.distance_km = None
    stamps = dict(activity.enrichment_versions)
    del stamps["enrichment_distance"]
    activity.enrichment_versions = stamps
    DB.session.commit()

    assert refresh_stale_enrichments(_config().activity_import()) == 1
    activity = _only_activity()
    assert activity.distance_km is not None
    assert activity.enrichment_versions == current_enrichment_versions()


def test_every_enrichment_carries_a_version(app_context) -> None:
    for enrichment in enrichments:
        assert isinstance(getattr(enrichment, "version", None), int), enrichment
