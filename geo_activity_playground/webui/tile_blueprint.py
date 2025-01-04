import io

import matplotlib.pyplot as pl
import numpy as np
from flask import Blueprint
from flask import Response

from geo_activity_playground.core.config import Config
from geo_activity_playground.core.raster_map import get_tile


def make_tile_blueprint(config: Config) -> Blueprint:
    blueprint = Blueprint("tiles", __name__, template_folder="templates")

    @blueprint.route("/color/<int:z>/<int:x>/<int:y>.png")
    def tile_color(x: int, y: int, z: int):
        map_tile = np.array(get_tile(z, x, y, config.map_tile_url)) / 255
        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")

    @blueprint.route("/grayscale/<int:z>/<int:x>/<int:y>.png")
    def tile_grayscale(x: int, y: int, z: int):
        map_tile = np.array(get_tile(z, x, y, config.map_tile_url)) / 255
        map_tile = np.sum(map_tile * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        map_tile = np.dstack((map_tile, map_tile, map_tile))  # to rgb
        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")

    @blueprint.route("/pastel/<int:z>/<int:x>/<int:y>.png")
    def tile_pastel(x: int, y: int, z: int):
        map_tile = np.array(get_tile(z, x, y, config.map_tile_url)) / 255
        averaged_tile = np.sum(map_tile * [0.2126, 0.7152, 0.0722], axis=2)
        grayscale_tile = np.dstack((averaged_tile, averaged_tile, averaged_tile))
        factor = 0.7
        pastel_tile = factor * grayscale_tile + (1 - factor) * map_tile
        f = io.BytesIO()
        pl.imsave(f, pastel_tile, format="png")
        return Response(bytes(f.getbuffer()), mimetype="image/png")

    return blueprint
