from .tiles import compute_tile
from .tiles import get_tile_upper_left_lat_lon
from .tiles import interpolate_missing_tile


def test_rheinbach() -> None:
    lat, lon = 50.6202, 6.9504
    assert compute_tile(lat, lon, 14) == (8508, 5512)


def test_back() -> None:
    tile_x, tile_y = 8508, 5512
    zoom = 14
    lat, lon = get_tile_upper_left_lat_lon(tile_x, tile_y, zoom)
    print(lat, lon)
    assert compute_tile(lat, lon, zoom) == (tile_x, tile_y)


def test_interpolate() -> None:
    assert interpolate_missing_tile(1.25, 2.25, 2.5, 1.5) == (1, 1)
    assert interpolate_missing_tile(2.5, 1.5, 1.25, 2.25) == (1, 1)
    assert interpolate_missing_tile(2.25, 2.5, 1.75, 1.25) == (2, 1)
    assert interpolate_missing_tile(1.25, 2.25, 2.25, 2.5) == None
