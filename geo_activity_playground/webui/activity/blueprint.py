import urllib.parse

import geojson
import matplotlib
import sqlalchemy
from flask import abort
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for

from ...core.activities import ActivityRepository
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.datamodel import Equipment
from ...core.datamodel import Kind
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from .controller import ActivityController


def make_activity_blueprint(
    activity_controller: ActivityController,
    repository: ActivityRepository,
    authenticator: Authenticator,
) -> Blueprint:
    blueprint = Blueprint("activity", __name__, template_folder="templates")

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

    @blueprint.route("/day-sharepic/<year>/<month>/<day>/sharepic.png")
    def day_sharepic(year: str, month: str, day: str):
        return Response(
            activity_controller.render_day_sharepic(int(year), int(month), int(day)),
            mimetype="image/png",
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
        activity = DB.session.get(Activity, int(id))
        if activity is None:
            abort(404)
        equipments = DB.session.scalars(sqlalchemy.select(Equipment)).all()
        kinds = DB.session.scalars(sqlalchemy.select(Kind)).all()

        if request.method == "POST":
            activity.name = request.form.get("name")

            form_equipment = request.form.get("equipment")
            if form_equipment == "null":
                activity.equipment = None
            else:
                activity.equipment = DB.session.get(Equipment, int(form_equipment))

            form_kind = request.form.get("kind")
            if form_kind == "null":
                activity.kind = None
            else:
                activity.kind = DB.session.get(Kind, int(form_kind))

            DB.session.commit()
            return redirect(url_for(".show", id=activity.id))

        return render_template(
            "activity/edit.html.j2",
            activity=activity,
            kinds=kinds,
            equipments=equipments,
        )

    @blueprint.route("/trim/<id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def trim(id: str):
        activity = DB.session.get(Activity, int(id))
        if activity is None:
            abort(404)

        if request.method == "POST":
            form_begin = request.form.get("begin")
            form_end = request.form.get("end")

            if form_begin:
                activity.index_begin = int(form_begin)
            if form_end:
                activity.index_end = int(form_end)

            DB.session.commit()

        cmap = matplotlib.colormaps["turbo"]
        num_points = len(activity.time_series)
        begin = activity.index_begin or 0
        end = activity.index_end or num_points

        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.LineString(
                        [
                            (lon, lat)
                            for lat, lon in zip(group["latitude"], group["longitude"])
                        ]
                    )
                )
                for _, group in activity.raw_time_series.groupby("segment_id")
            ]
            + [
                geojson.Feature(
                    geometry=geojson.Point(
                        (lon, lat),
                    ),
                    properties={
                        "name": f"{index}",
                        "markerType": "circle",
                        "markerStyle": {
                            "fillColor": matplotlib.colors.to_hex(
                                cmap(1 - index / num_points)
                            ),
                            "fillOpacity": 0.5,
                            "radius": 8,
                            "color": "black" if begin <= index < end else "white",
                            "opacity": 0.8,
                            "weight": 2,
                        },
                    },
                )
                for _, group in activity.raw_time_series.groupby("segment_id")
                for index, lat, lon in zip(
                    group.index, group["latitude"], group["longitude"]
                )
            ]
        )
        return render_template(
            "activity/trim.html.j2",
            activity=activity,
            color_line_geojson=geojson.dumps(fc),
        )

    return blueprint
