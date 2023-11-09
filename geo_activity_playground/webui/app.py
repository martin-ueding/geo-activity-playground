import pathlib

from flask import Flask
from flask import render_template


def webui_main(basedir: pathlib.Path) -> None:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/explorer")
    def explorer():
        return render_template("explorer.html")

    @app.route("/explored-tiles.geojson")
    def explored_tiles():
        with open(basedir / "Explorer" / "explored.geojson") as f:
            return f.read()

    app.run()
