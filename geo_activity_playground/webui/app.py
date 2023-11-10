import itertools
import pathlib

from flask import Flask
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.plots import activity_track_plot
from geo_activity_playground.explorer.grid_file import get_explored_geojson


def webui_main(basedir: pathlib.Path, repository: ActivityRepository) -> None:
    app = Flask(__name__)

    @app.route("/")
    def index():
        activities = list(itertools.islice(repository.iter_activities(), 20))
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

    app.run()
