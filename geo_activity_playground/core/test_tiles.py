from .tiles import compute_tile
from .tiles import get_tile_upper_left_lat_lon


def test_rheinbach() -> None:
    lat, lon = 50.6202, 6.9504
    assert compute_tile(lat, lon) == (8508, 5512)


def test_back() -> None:
    tile_x, tile_y = 8508, 5512
    zoom = 14
    lat, lon = get_tile_upper_left_lat_lon(tile_x, tile_y, zoom)
    print(lat, lon)
    assert compute_tile(lat, lon, zoom) == (tile_x, tile_y)
