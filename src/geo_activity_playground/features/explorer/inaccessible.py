import sqlalchemy

from ...core.datamodel import DB
from .model import InaccessibleTile


def get_inaccessible_tiles(
    zoom: int, x_min: int, x_max: int, y_min: int, y_max: int
) -> frozenset[tuple[int, int]]:
    return frozenset(
        (tile.tile_x, tile.tile_y)
        for tile in DB.session.scalars(
            sqlalchemy.select(InaccessibleTile).where(
                InaccessibleTile.zoom == zoom,
                InaccessibleTile.tile_x >= x_min,
                InaccessibleTile.tile_x <= x_max,
                InaccessibleTile.tile_y >= y_min,
                InaccessibleTile.tile_y <= y_max,
            )
        )
    )
