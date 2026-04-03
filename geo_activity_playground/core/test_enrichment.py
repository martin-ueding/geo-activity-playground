import pandas as pd

from . import enrichment
from .config import Config
from .datamodel import Activity


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

    enrichment.update_and_commit(activity, time_series, Config())

    assert calls == []
