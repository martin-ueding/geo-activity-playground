from flask import Blueprint
from flask import render_template

from .controller import EddingtonController


def make_eddington_blueprint(eddington_controller: EddingtonController) -> Blueprint:
    blueprint = Blueprint("eddington", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        return render_template(
            "eddington/index.html.j2", **eddington_controller.render()
        )

    return blueprint
