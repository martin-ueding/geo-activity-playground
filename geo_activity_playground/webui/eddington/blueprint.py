from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository
from .controller import EddingtonController


def make_eddington_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("eddington", __name__, template_folder="templates")

    eddington_controller = EddingtonController(repository)

    @blueprint.route("/")
    def index():
        return render_template(
            "eddington/index.html.j2", **eddington_controller.render()
        )

    return blueprint
