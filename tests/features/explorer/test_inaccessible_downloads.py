import pandas as pd

from geo_activity_playground.core.coordinates import Bounds
from geo_activity_playground.core.datamodel import DB
from geo_activity_playground.core.grid import get_border_tiles
from geo_activity_playground.features.explorer.inaccessible import (
    get_inaccessible_tiles,
)
from geo_activity_playground.features.explorer.model import InaccessibleTile


def test_get_border_tiles_skips_excluded_tiles() -> None:
    tiles = pd.DataFrame({"tile_x": [10], "tile_y": [10]})
    bounds = Bounds(10, 10, 12, 12)

    without_exclusion = get_border_tiles(tiles, 14, bounds)
    with_exclusion = get_border_tiles(tiles, 14, bounds, frozenset({(11, 10)}))

    assert len(without_exclusion) == 3
    assert len(with_exclusion) == 2


def test_inaccessible_tiles_are_limited_to_bounds(app_context: None) -> None:
    DB.session.add(InaccessibleTile(zoom=14, tile_x=11, tile_y=10))  # pyright: ignore
    DB.session.add(InaccessibleTile(zoom=14, tile_x=20, tile_y=10))  # pyright: ignore
    DB.session.add(InaccessibleTile(zoom=17, tile_x=11, tile_y=10))  # pyright: ignore
    DB.session.commit()

    assert get_inaccessible_tiles(14, 10, 12, 10, 12) == frozenset({(11, 10)})
