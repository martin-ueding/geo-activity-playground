from ..core.datamodel import Kind
from . import activity_parsers


def test_read_activity_gpx_extracts_track_name_and_type(tmp_path, monkeypatch) -> None:
    path = tmp_path / "activity.gpx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Abendlauf</name>
    <type>running</type>
    <trkseg>
      <trkpt lat="49.0" lon="8.0">
        <ele>123.4</ele>
        <time>2026-01-01T18:00:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        activity_parsers, "get_or_make_kind", lambda name: Kind(name=name)
    )

    activity, timeseries = activity_parsers.read_activity(path)

    assert activity.name == "Abendlauf"
    assert activity.kind is not None
    assert activity.kind.name == "running"
    assert len(timeseries) == 1


def test_read_activity_gpx_without_track_metadata(tmp_path) -> None:
    path = tmp_path / "activity.gpx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <trkseg>
      <trkpt lat="49.0" lon="8.0">
        <time>2026-01-01T18:00:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
""",
        encoding="utf-8",
    )

    activity, timeseries = activity_parsers.read_activity(path)

    assert activity.name is None
    assert activity.kind is None
    assert len(timeseries) == 1
