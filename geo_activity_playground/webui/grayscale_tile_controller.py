import io

import matplotlib.pyplot as pl
import numpy as np

from geo_activity_playground.core.tiles import get_tile


class GrayscaleTileController:
    def render_tile(self, x: int, y: int, z: int) -> bytes:
        map_tile = np.array(get_tile(z, x, y)) / 255
        map_tile = np.sum(map_tile * [0.2126, 0.7152, 0.0722], axis=2)  # to grayscale
        map_tile = np.dstack((map_tile, map_tile, map_tile))  # to rgb
        f = io.BytesIO()
        pl.imsave(f, map_tile, format="png")
        return bytes(f.getbuffer())
