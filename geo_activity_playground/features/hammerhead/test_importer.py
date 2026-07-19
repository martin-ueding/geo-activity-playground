from .importer import _max_date


def test_max_date_picks_newer() -> None:
    assert _max_date(None, "2026-01-01T00:00:00Z") == "2026-01-01T00:00:00Z"
    assert (
        _max_date("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
        == "2026-02-01T00:00:00Z"
    )
    assert (
        _max_date("2026-02-01T00:00:00Z", "2026-01-01T00:00:00Z")
        == "2026-02-01T00:00:00Z"
    )
