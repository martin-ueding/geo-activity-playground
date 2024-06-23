from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository
from .controller import CalendarController


def make_calendar_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("calendar", __name__, template_folder="templates")

    calendar_controller = CalendarController(repository)

    @blueprint.route("/")
    def index():
        return render_template(
            "calendar/index.html.j2", **calendar_controller.render_overview()
        )

    @blueprint.route("/<year>/<month>")
    def month(year: str, month: str):
        return render_template(
            "calendar/month.html.j2",
            **calendar_controller.render_month(int(year), int(month))
        )

    return blueprint
