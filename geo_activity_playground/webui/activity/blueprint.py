import json
import urllib.parse
from collections.abc import Collection

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .controller import ActivityController
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.paths import activity_meta_override_dir
from geo_activity_playground.core.privacy_zones import PrivacyZone
from geo_activity_playground.webui.authenticator import Authenticator
from geo_activity_playground.webui.authenticator import needs_authentication


def make_activity_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("activity", __name__, template_folder="templates")

    activity_controller = ActivityController(repository, tile_visit_accessor, config)

    @blueprint.route("/all")
    def all():
        return render_template(
            "activity/lines.html.j2", **activity_controller.render_all()
        )

    @blueprint.route("/<id>")
    def show(id: str):
        return render_template(
            "activity/show.html.j2", **activity_controller.render_activity(int(id))
        )

    @blueprint.route("/<id>/sharepic.png")
    def sharepic(id: str):
        return Response(
            activity_controller.render_sharepic(int(id)),
            mimetype="image/png",
        )

    @blueprint.route("/day/<year>/<month>/<day>")
    def day(year: str, month: str, day: str):
        return render_template(
            "activity/day.html.j2",
            **activity_controller.render_day(int(year), int(month), int(day)),
        )

    @blueprint.route("/name/<name>")
    def name(name: str):
        return render_template(
            "activity/name.html.j2",
            **activity_controller.render_name(urllib.parse.unquote(name)),
        )

    @blueprint.route("/edit/<id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def edit(id: str):
        activity_id = int(id)
        activity = repository.get_activity_by_id(activity_id)
        override_file = activity_meta_override_dir() / f"{activity_id}.json"
        if override_file.exists():
            with open(override_file) as f:
                override = json.load(f)
        else:
            override = {}

        if request.method == "POST":
            override = {}
            if value := request.form.get("name"):
                override["name"] = value
                repository.meta.loc[activity_id, "name"] = value
            if value := request.form.get("kind"):
                override["kind"] = value
                repository.meta.loc[activity_id, "kind"] = value
            if value := request.form.get("equipment"):
                override["equipment"] = value
                repository.meta.loc[activity_id, "equipment"] = value
            if value := request.form.get("commute"):
                override["commute"] = True
                repository.meta.loc[activity_id, "commute"] = True
            if value := request.form.get("consider_for_achievements"):
                override["consider_for_achievements"] = True
                repository.meta.loc[activity_id, "consider_for_achievements"] = True

            with open(override_file, "w") as f:
                json.dump(override, f, ensure_ascii=False, indent=4, sort_keys=True)

            repository.save()

            return redirect(url_for(".show", id=activity_id))

        return render_template(
            "activity/edit.html.j2",
            activity_id=activity_id,
            activity=activity,
            override=override,
        )

    return blueprint
