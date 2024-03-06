import io

import matplotlib.pyplot as pl
import numpy as np

from geo_activity_playground.core.tiles import get_tile


class TileController:
    def render_color(self, x: int, y: int, z: int) -> bytes:
        map_tile = np.array(get_tile(z, x, y)) / 255
        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return bytes(f.getbuffer())

    def render_grayscale(self, x: int, y: int, z: int) -> bytes:
        map_tile = np.array(get_tile(z, x, y)) / 255
        map_tile = np.sum(map_tile * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        map_tile = np.dstack((map_tile, map_tile, map_tile))  # to rgb
        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return bytes(f.getbuffer())

    def render_pastel(self, x: int, y: int, z: int) -> bytes:
        map_tile = np.array(get_tile(z, x, y)) / 255
        averaged_tile = np.sum(map_tile * [0.2126, 0.7152, 0.0722], axis=2)
        grayscale_tile = np.dstack((averaged_tile, averaged_tile, averaged_tile))
        factor = 0.7
        pastel_tile = factor * grayscale_tile + (1 - factor) * map_tile
        f = io.BytesIO()
        pl.imsave(f, pastel_tile, format="png")
        return bytes(f.getbuffer())
