from .hammerhead_api import _max_date, _tokens_from_response


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


def test_tokens_from_response_uses_expires_in() -> None:
    tokens = _tokens_from_response(
        {"access_token": "a", "refresh_token": "r", "expires_in": 3600}
    )
    assert tokens["access"] == "a"
    assert tokens["refresh"] == "r"
    assert tokens["expires_at"] > 0
