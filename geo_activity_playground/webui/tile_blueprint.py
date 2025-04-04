import abc
import io

import matplotlib.pyplot as pl
import numpy as np
from flask import Blueprint
from flask import Flask
from flask import Response
from flask.views import View

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


class ImageTransform:
    @abc.abstractmethod
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        pass


class IdentityImageTransform(ImageTransform):
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        return image


class GrayscaleImageTransform(ImageTransform):
    def transform_image(self, image: np.ndarray) -> np.ndarray:
        image = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        return np.dstack((image, image, image))  # to rgb


class PastelImageTransform(ImageTransform):
    def __init__(self, factor: float = 0.7):
        self._factor = factor

    def transform_image(self, image: np.ndarray) -> np.ndarray:
        averaged_tile = np.sum(image * [0.2126, 0.7152, 0.0722], axis=2)
        grayscale_tile = np.dstack((averaged_tile, averaged_tile, averaged_tile))
        return self._factor * grayscale_tile + (1 - self._factor) * image


class TileGetter:
    def __init__(self, map_tile_url: str):
        self._map_tile_url = map_tile_url

    def get_tile(
        self,
        z: int,
        x: int,
        y: int,
    ):
        return get_tile(z, x, y, self._map_tile_url)


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


def register_tile_routes(app: Flask, config: Config):
    tile_getter = TileGetter(config.map_tile_url)

    app.add_url_rule(
        "/tile/color/<int:z>/<int:x>/<int:y>.png",
        view_func=TileView.as_view("tile_color", IdentityImageTransform(), tile_getter),
    )
    app.add_url_rule(
        "/tile/grayscale/<int:z>/<int:x>/<int:y>.png",
        view_func=TileView.as_view(
            "tile_grayscale", GrayscaleImageTransform(), tile_getter
        ),
    )
    app.add_url_rule(
        "/tile/pastel/<int:z>/<int:x>/<int:y>.png",
        view_func=TileView.as_view("tile_pastel", PastelImageTransform(), tile_getter),
    )
