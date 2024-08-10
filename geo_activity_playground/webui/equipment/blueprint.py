from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository
from .controller import EquipmentController
from geo_activity_playground.core.config import Config


def make_equipment_blueprint(
    repository: ActivityRepository, config: Config
) -> Blueprint:
    blueprint = Blueprint("equipment", __name__, template_folder="templates")

    equipment_controller = EquipmentController(repository, config)

    @blueprint.route("/")
    def index():
        return render_template(
            "equipment/index.html.j2", **equipment_controller.render()
        )

    return blueprint
