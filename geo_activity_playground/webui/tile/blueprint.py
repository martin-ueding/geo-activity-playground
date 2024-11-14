from flask import Blueprint
from flask import Response

from .controller import TileController
from geo_activity_playground.core.config import Config


def make_tile_blueprint(config: Config) -> Blueprint:
    blueprint = Blueprint("tiles", __name__, template_folder="templates")

    tile_controller = TileController(config)

    @blueprint.route("/color/<z>/<x>/<y>.png")
    def tile_color(x: str, y: str, z: str):
        return Response(
            tile_controller.render_color(int(x), int(y), int(z)), mimetype="image/png"
        )

    @blueprint.route("/grayscale/<z>/<x>/<y>.png")
    def tile_grayscale(x: str, y: str, z: str):
        return Response(
            tile_controller.render_grayscale(int(x), int(y), int(z)),
            mimetype="image/png",
        )

    @blueprint.route("/pastel/<z>/<x>/<y>.png")
    def tile_pastel(x: str, y: str, z: str):
        return Response(
            tile_controller.render_pastel(int(x), int(y), int(z)), mimetype="image/png"
        )

    return blueprint
