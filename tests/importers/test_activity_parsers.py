import datetime
from types import SimpleNamespace

import fitdecode

from geo_activity_playground.core.datamodel import Kind
from geo_activity_playground.importers import activity_parsers


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


def _fit_frame(
    name: str, units: dict[str, str] | None = None, **values
) -> SimpleNamespace:
    return SimpleNamespace(
        frame_type=fitdecode.FIT_FRAME_DATA,
        name=name,
        fields=[
            SimpleNamespace(name=key, value=value, units=(units or {}).get(key))
            for key, value in values.items()
        ],
    )


class _FakeFitReader:
    def __init__(self, frames: list[SimpleNamespace]) -> None:
        self.frames = frames

    def __call__(self, _file) -> "_FakeFitReader":
        return self

    def __enter__(self) -> list[SimpleNamespace]:
        return self.frames

    def __exit__(self, *args) -> None:
        pass


def test_read_fit_activity_takes_steps_from_session_before_laps(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "activity.fit"
    path.write_bytes(b"")
    frames = [
        _fit_frame("session", total_strides=1513, total_calories=250),
        _fit_frame("lap", total_strides=658, total_calories=110),
        _fit_frame("lap", total_strides=655, total_calories=105),
        _fit_frame("lap", total_strides=200, total_calories=35),
    ]
    monkeypatch.setattr(fitdecode, "FitReader", _FakeFitReader(frames))

    activity, _ = activity_parsers.read_fit_activity(path, open)

    assert activity.steps == 3026
    assert activity.calories == 250


def test_read_fit_activity_keeps_zero_values(tmp_path, monkeypatch) -> None:
    path = tmp_path / "activity.fit"
    path.write_bytes(b"")
    frames = [
        _fit_frame(
            "record",
            units={"enhanced_speed": "m/s"},
            timestamp=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
            position_lat=600_000_000,
            position_long=100_000_000,
            enhanced_speed=0.0,
            cadence=0,
            power=0,
            enhanced_altitude=0.0,
        ),
        _fit_frame("workout", wkt_name=""),
    ]
    monkeypatch.setattr(fitdecode, "FitReader", _FakeFitReader(frames))

    activity, time_series = activity_parsers.read_fit_activity(path, open)

    assert time_series[["speed", "cadence", "power", "elevation"]].iloc[
        0
    ].to_list() == [
        0.0,
        0,
        0,
        0.0,
    ]
    assert activity.name is None
