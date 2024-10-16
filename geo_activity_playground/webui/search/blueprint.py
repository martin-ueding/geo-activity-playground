from flask import Blueprint
from flask import render_template
from flask import request
from flask import Response

from ...core.activities import ActivityRepository


def make_search_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        kinds_avail = repository.meta["kind"].unique()

        print(request.form)

        # activities = []
        # for _, row in repository.meta.iterrows():
        #     if request.form["name"] in row["name"]:
        #         activities.append(row)
        return render_template(
            "search/index.html.j2",
            kinds=request.form.get("kind", []),
            kinds_avail=sorted(kinds_avail),
        )

    return blueprint
