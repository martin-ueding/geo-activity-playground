import urllib.parse
from collections.abc import Collection

from flask import Blueprint
from flask import render_template
from flask import Response

from ...core.activities import ActivityRepository
from ...explorer.tile_visits import TileVisitAccessor
from .controller import ActivityController
from geo_activity_playground.core.privacy_zones import PrivacyZone


def make_activity_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    privacy_zones: Collection[PrivacyZone],
) -> Blueprint:
    blueprint = Blueprint("activity", __name__, template_folder="templates")

    activity_controller = ActivityController(
        repository, tile_visit_accessor, privacy_zones
    )

    @blueprint.route("/activity/all")
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
            **activity_controller.render_day(int(year), int(month), int(day))
        )

    @blueprint.route("/name/<name>")
    def name(name: str):
        return render_template(
            "activity/name.html.j2",
            **activity_controller.render_name(urllib.parse.unquote(name))
        )

    return blueprint
