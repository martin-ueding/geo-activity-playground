from .tiles import compute_tile


def test_rheinbach() -> None:
    lat, lon = 50.6202, 6.9504
    assert compute_tile(lat, lon) == (8508, 5512)
