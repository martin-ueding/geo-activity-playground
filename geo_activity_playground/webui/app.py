import itertools
import pathlib

from flask import Flask
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.plots import activity_track_plot
from geo_activity_playground.core.plots import meta_plots
from geo_activity_playground.explorer.grid_file import get_explored_geojson
from geo_activity_playground.webui.calendar import CalendarController
from geo_activity_playground.webui.eddington import EddingtonController


def webui_main(basedir: pathlib.Path, repository: ActivityRepository) -> None:
    app = Flask(__name__)

    calendar_controller = CalendarController(repository)
    eddington_controller = EddingtonController(repository)

    @app.route("/")
    def index():
        activities = list(itertools.islice(repository.iter_activities(), 50))
        return render_template("index.html", activities=activities)

    @app.route("/activity/<id>")
    def activity(id: int):
        activity = repository.get_activity_by_id(int(id))
        return render_template("activity.html", activity=activity)

    @app.route("/activity/<id>/track.json")
    def activity_track(id: int):
        plot = activity_track_plot(repository.get_time_series(int(id)))
        return plot

    @app.route("/explorer")
    def explorer():
        return render_template("explorer.html")

    @app.route("/explored-tiles.geojson")
    def explored_tiles():
        return get_explored_geojson(repository)

    @app.route("/summary-statistics")
    def summary_statistics():
        return render_template("summary-statistics.html")

    @app.route("/meta-plot/<name>.json")
    def meta_plot(name: str):
        return meta_plots[name](repository.meta.reset_index())

    @app.route("/eddington")
    def eddington():
        return render_template("eddington.html", **eddington_controller.render())

    @app.route("/calendar")
    def calendar():
        return render_template("calendar.html", **calendar_controller.render_overview())

    @app.route("/calendar/<year>/<month>")
    def calendar_year_month(year: str, month: str):
        return render_template(
            "calendar-month.html",
            **calendar_controller.render_month(int(year), int(month))
        )

    app.run()
