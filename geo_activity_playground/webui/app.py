import pathlib

from flask import Flask
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.plots import activity_track_plot
from geo_activity_playground.core.plots import meta_plots
from geo_activity_playground.webui.activity_controller import ActivityController
from geo_activity_playground.webui.calendar_controller import CalendarController
from geo_activity_playground.webui.eddington_controller import EddingtonController
from geo_activity_playground.webui.entry_controller import EntryController
from geo_activity_playground.webui.explorer_controller import ExplorerController


def webui_main(basedir: pathlib.Path, repository: ActivityRepository) -> None:
    app = Flask(__name__)

    entry_controller = EntryController(repository)
    calendar_controller = CalendarController(repository)
    eddington_controller = EddingtonController(repository)
    activity_controller = ActivityController(repository)
    explorer_controller = ExplorerController(repository)

    @app.route("/")
    def index():
        return render_template("index.html.j2", **entry_controller.render())

    @app.route("/activity/<id>")
    def activity(id: int):
        return render_template(
            "activity.html.j2", **activity_controller.render_activity(int(id))
        )

    @app.route("/activity/<id>/track.json")
    def activity_track(id: int):
        plot = activity_track_plot(repository.get_time_series(int(id)))
        return plot

    @app.route("/explorer")
    def explorer():
        return render_template("explorer.html.j2", **explorer_controller.render())

    @app.route("/summary-statistics")
    def summary_statistics():
        return render_template("summary-statistics.html.j2")

    @app.route("/meta-plot/<name>.json")
    def meta_plot(name: str):
        return meta_plots[name](repository.meta.reset_index())

    @app.route("/eddington")
    def eddington():
        return render_template("eddington.html.j2", **eddington_controller.render())

    @app.route("/calendar")
    def calendar():
        return render_template(
            "calendar.html.j2", **calendar_controller.render_overview()
        )

    @app.route("/calendar/<year>/<month>")
    def calendar_year_month(year: str, month: str):
        return render_template(
            "calendar-month.html.j2",
            **calendar_controller.render_month(int(year), int(month))
        )

    app.run()
