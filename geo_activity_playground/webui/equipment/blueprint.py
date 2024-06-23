from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository
from .controller import EquipmentController


def make_equipment_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("equipment", __name__, template_folder="templates")

    equipment_controller = EquipmentController(repository)

    @blueprint.route("/")
    def index():
        return render_template(
            "equipment/index.html.j2", **equipment_controller.render()
        )

    return blueprint
