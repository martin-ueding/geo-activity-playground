import io

import matplotlib.pyplot as pl
import numpy as np
from flask import Flask
from flask import Response
from flask.views import View

from geo_activity_playground.core.raster_map import GrayscaleImageTransform
from geo_activity_playground.core.raster_map import IdentityImageTransform
from geo_activity_playground.core.raster_map import ImageTransform
from geo_activity_playground.core.raster_map import PastelImageTransform
from geo_activity_playground.core.raster_map import TileGetter


class TileView(View):
    def __init__(
        self, image_transforms: dict[str, ImageTransform], tile_getter: TileGetter
    ) -> None:
        self._image_transforms = image_transforms
        self._tile_getter = tile_getter

    def dispatch_request(self, scheme: str, z: int, x: int, y: int) -> Response:
        map_tile = np.array(self._tile_getter.get_tile(z, x, y)) / 255
        transformed_tile = self._image_transforms[scheme].transform_image(map_tile)
        f = io.BytesIO()
        pl.imsave(f, transformed_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")


def register_tile_routes(app: Flask, tile_getter: TileGetter):
    app.add_url_rule(
        "/tile/<scheme>/<int:z>/<int:x>/<int:y>.png",
        "tile",
        TileView(
            {
                "color": IdentityImageTransform(),
                "grayscale": GrayscaleImageTransform(),
                "pastel": PastelImageTransform(),
            },
            tile_getter,
        ).dispatch_request,
    )
