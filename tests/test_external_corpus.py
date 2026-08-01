"""Parse an out-of-repository corpus of activity files.

Files contributed by other users cannot be committed here, but they are the
best source of parser edge cases. Point ``GAP_TEST_CORPUS`` at a directory of
such files and this module checks that each of them still parses. Without the
variable the whole module is skipped.
"""

import os
import pathlib

import pytest

from geo_activity_playground.core.datamodel import Activity
from geo_activity_playground.importers.activity_parsers import read_activity

SUFFIXES = {".gpx", ".fit", ".tcx", ".kml", ".kmz", ".csv", ".gz"}

_corpus_dir = os.environ.get("GAP_TEST_CORPUS")

pytestmark = pytest.mark.skipif(not _corpus_dir, reason="GAP_TEST_CORPUS is not set")


def _corpus_files() -> list[pathlib.Path]:
    if not _corpus_dir:
        return []
    return sorted(
        path
        for path in pathlib.Path(_corpus_dir).rglob("*")
        if path.is_file() and path.suffix.lower() in SUFFIXES
    )


@pytest.mark.parametrize("path", _corpus_files(), ids=str)
def test_corpus_file_parses(path: pathlib.Path, app_context) -> None:
    activity, time_series = read_activity(path)

    assert isinstance(activity, Activity)
    assert len(time_series) > 0
    assert "time" in time_series.columns
    assert {"latitude", "longitude"} <= set(time_series.columns)
