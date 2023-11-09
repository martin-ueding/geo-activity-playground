import itertools
import pathlib

from flask import Flask
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository


def webui_main(basedir: pathlib.Path, repository: ActivityRepository) -> None:
    app = Flask(__name__)

    @app.route("/")
    def index():
        activities = list(itertools.islice(repository.iter_activities(), 20))
        return render_template("index.html", activities=activities)

    @app.route("/activity/<id>")
    def activities(id: int):
        activity = repository.get_activity_by_id(id)
        return render_template("activity.html", activity=activity)

    @app.route("/explorer")
    def explorer():
        return render_template("explorer.html")

    @app.route("/explored-tiles.geojson")
    def explored_tiles():
        with open(basedir / "Explorer" / "explored.geojson") as f:
            return f.read()

    app.run()
