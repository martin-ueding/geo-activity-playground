from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response

from ...core.activities import ActivityRepository


def make_search_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

    @blueprint.route("/", methods=["POST"])
    def index():
        activities = []
        for _, row in repository.meta.iterrows():
            if request.form["name"] in row["name"]:
                activities.append(row)
        return render_template("search/index.html.j2", activities=activities)

    return blueprint
