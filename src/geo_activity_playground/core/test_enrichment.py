import numpy as np
import pandas as pd

from . import enrichment
from .datamodel import Activity, ActivityImportConfig


def test_update_and_commit_skips_single_track_point(monkeypatch) -> None:
    calls: list[str] = []

    def fake_apply_tag_extraction(_activity) -> None:
        calls.append("tag")

    def fake_apply_enrichments(_activity, _time_series, _config, _force) -> bool:
        calls.append("enrich")
        return True

    class DummySession:
        def add(self, _activity) -> None:
            calls.append("add")

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(
        enrichment, "apply_tag_extraction_from_database", fake_apply_tag_extraction
    )
    monkeypatch.setattr(enrichment, "apply_enrichments", fake_apply_enrichments)
    monkeypatch.setattr(enrichment.DB, "session", DummySession())

    activity = Activity(name="One Point")
    time_series = pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-01-01T00:00:00Z"),
                "latitude": 50.0,
                "longitude": 8.0,
            }
        ]
    )

    enrichment.update_and_commit(activity, time_series, ActivityImportConfig())

    assert calls == []


def test_gps_spike_filtered_by_acceleration() -> None:
    """A short-lived speed spike caused by a GPS error should be removed even if the
    absolute speed change is below the old 100 km/h-per-sample threshold."""
    # Simulate 1-second samples: 15 km/h steady → 75 km/h spike → 15 km/h steady.
    # The rise/fall rate is 60 km/h/s >> 20 km/h/s threshold.
    activity = Activity(name="Spike test")
    activity.index_begin = 0
    activity.index_end = None
    time_series = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2026-01-01T00:00:00Z"] * 5,
            )
            + pd.to_timedelta([0, 1, 2, 3, 4], unit="s"),
            "latitude": [50.0] * 5,
            "longitude": [8.0] * 5,
            "speed": [15.0, 15.0, 75.0, 15.0, 15.0],
            "distance_km": [0.0, 0.004, 0.025, 0.046, 0.050],
        }
    )
    enrichment.enrichment_distance(
        activity,
        time_series,
        ActivityImportConfig(time_diff_threshold_seconds=30),
        force=False,
    )
    assert not np.isnan(time_series.loc[2, "speed"]), (
        "Spike should be interpolated, not left as NaN"
    )
    assert time_series.loc[2, "speed"] < 50.0, "GPS spike should have been smoothed out"


def test_sustained_high_speed_not_filtered() -> None:
    """A legitimate high speed that is sustained across multiple samples must not be removed."""
    activity = Activity(name="Fast ride")
    activity.index_begin = 0
    activity.index_end = None
    time_series = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2026-01-01T00:00:00Z"] * 5,
            )
            + pd.to_timedelta([0, 1, 2, 3, 4], unit="s"),
            "latitude": [50.0] * 5,
            "longitude": [8.0] * 5,
            "speed": [10.0, 40.0, 80.0, 80.0, 80.0],
            "distance_km": [0.0, 0.014, 0.036, 0.058, 0.080],
        }
    )
    enrichment.enrichment_distance(
        activity,
        time_series,
        ActivityImportConfig(time_diff_threshold_seconds=30),
        force=False,
    )
    assert time_series.loc[4, "speed"] > 70.0, (
        "Sustained high speed should not be filtered"
    )
