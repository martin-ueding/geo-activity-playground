import io

import matplotlib.pyplot as pl
import numpy as np
from flask import Flask
from flask import Response

from geo_activity_playground.core.raster_map import ImageTransform
from geo_activity_playground.core.raster_map import TileGetter
from geo_activity_playground.webui.interfaces import MyView


class TileView(MyView):
    def __init__(
        self, image_transforms: dict[str, ImageTransform], tile_getter: TileGetter
    ) -> None:
        self._image_transforms = image_transforms
        self._tile_getter = tile_getter

    def register(self, app: Flask) -> None:
        app.add_url_rule(
            "/tile/<scheme>/<int:z>/<int:x>/<int:y>.png", "tile", self.dispatch
        )

    def dispatch(self, scheme: str, z: int, x: int, y: int) -> Response:
        map_tile = np.array(self._tile_getter.get_tile(z, x, y)) / 255
        transformed_tile = self._image_transforms[scheme].transform_image(map_tile)
        f = io.BytesIO()
        pl.imsave(f, transformed_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")
