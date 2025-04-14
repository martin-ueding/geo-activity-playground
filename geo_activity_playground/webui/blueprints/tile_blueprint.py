import io

import matplotlib.pyplot as pl
import numpy as np
from flask import Blueprint
from flask import Response

from ...core.raster_map import ImageTransform
from ...core.raster_map import TileGetter


def make_tile_blueprint(
    image_transforms: dict[str, ImageTransform],
    tile_getter: TileGetter,
) -> Blueprint:

    blueprint = Blueprint("tile", __name__, template_folder="templates")

    @blueprint.route("/<scheme>/<int:z>/<int:x>/<int:y>.png")
    def tile(scheme: str, z: int, x: int, y: int) -> Response:
        map_tile = np.array(tile_getter.get_tile(z, x, y)) / 255
        transformed_tile = image_transforms[scheme].transform_image(map_tile)
        f = io.BytesIO()
        pl.imsave(f, transformed_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")

    return blueprint
