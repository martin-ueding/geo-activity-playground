from flask import Blueprint
from flask import render_template

from geo_activity_playground.webui.calendar.controller import CalendarController


def make_calendar_blueprint(calendar_controller: CalendarController) -> Blueprint:
    blueprint = Blueprint("calendar", __name__, template_folder="templates")

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
