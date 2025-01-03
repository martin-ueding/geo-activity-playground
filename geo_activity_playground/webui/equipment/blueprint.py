from flask import Blueprint
from flask import render_template

from geo_activity_playground.webui.equipment.controller import EquipmentController


def make_equipment_blueprint(equipment_controller: EquipmentController) -> Blueprint:
    blueprint = Blueprint("equipment", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        return render_template(
            "equipment/index.html.j2", **equipment_controller.render()
        )

    return blueprint
