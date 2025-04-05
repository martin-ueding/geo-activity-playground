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
        self, image_transform: ImageTransform, tile_getter: TileGetter
    ) -> None:
        self._image_transform = image_transform
        self._tile_getter = tile_getter

    def dispatch_request(self, z: int, x: int, y: int) -> Response:
        map_tile = np.array(self._tile_getter.get_tile(z, x, y)) / 255
        transformed_tile = self._image_transform.transform_image(map_tile)
        f = io.BytesIO()
        pl.imsave(f, transformed_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")


def register_tile_routes(app: Flask, tile_getter: TileGetter):
    app.add_url_rule(
        "/tile/color/<int:z>/<int:x>/<int:y>.png",
        "tile_color",
        TileView(IdentityImageTransform(), tile_getter).dispatch_request,
    )
    app.add_url_rule(
        "/tile/grayscale/<int:z>/<int:x>/<int:y>.png",
        "tile_grayscale",
        TileView(GrayscaleImageTransform(), tile_getter).dispatch_request,
    )
    app.add_url_rule(
        "/tile/pastel/<int:z>/<int:x>/<int:y>.png",
        "tile_pastel",
        TileView(PastelImageTransform(), tile_getter).dispatch_request,
    )
