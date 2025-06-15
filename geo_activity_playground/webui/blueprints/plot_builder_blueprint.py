import json

import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for
from flask.typing import ResponseReturnValue
from flask.typing import RouteCallable

from ...core.activities import ActivityRepository
from ...core.datamodel import DB
from ...core.parametric_plot import GROUP_BY_VARIABLES
from ...core.parametric_plot import make_parametric_plot
from ...core.parametric_plot import MARKS
from ...core.parametric_plot import PlotSpec
from ...core.parametric_plot import VARIABLES_1
from ...core.parametric_plot import VARIABLES_2
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes


def make_plot_builder_blueprint(
    repository: ActivityRepository, flasher: Flasher, authenticator: Authenticator
) -> Blueprint:
    blueprint = Blueprint("plot_builder", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        return render_template(
            "plot_builder/index.html.j2",
            specs=DB.session.scalars(sqlalchemy.select(PlotSpec)).all(),
        )

    @blueprint.route("/new")
    @needs_authentication(authenticator)
    def new() -> ResponseReturnValue:
        spec = PlotSpec(
            name="My New Plot",
            mark="bar",
            x="year(start):O",
            y="sum(distance_km)",
            color="kind",
        )
        DB.session.add(spec)
        DB.session.commit()
        return redirect(url_for(".edit", id=spec.id))

    @blueprint.route("/import-spec", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def import_spec() -> ResponseReturnValue:
        if request.form:
            parameters = json.loads(request.form["spec_json"])
            spec = PlotSpec(**parameters)
            DB.session.add(spec)
            DB.session.commit()
            return redirect(url_for(".edit", id=spec.id))
        else:
            return render_template("plot_builder/import-spec.html.j2")

    @blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def edit(id: int) -> ResponseReturnValue:
        spec = DB.session.get_one(PlotSpec, id)
        if request.form:
            spec.name = request.form["name"]
            spec.mark = request.form["mark"]
            spec.x = request.form["x"]
            spec.y = request.form["y"]
            spec.color = request.form["color"]
            spec.shape = request.form["shape"]
            spec.size = request.form["size"]
            spec.size = request.form["size"]
            spec.row = request.form["row"]
            spec.column = request.form["column"]
            spec.facet = request.form["facet"]
            spec.opacity = request.form["opacity"]
            spec.group_by = request.form["group_by"]
        try:
            plot = make_parametric_plot(repository.meta, spec)
            DB.session.commit()
        except ValueError as e:
            plot = None
            flasher.flash_message(str(e), FlashTypes.WARNING)
        return render_template(
            "plot_builder/edit.html.j2",
            marks=MARKS,
            discrete=VARIABLES_1,
            continuous=VARIABLES_2,
            group_by=GROUP_BY_VARIABLES,
            plot=plot,
            spec=spec,
        )

    @blueprint.route("/delete/<int:id>")
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        spec = DB.session.get(PlotSpec, id)
        DB.session.delete(spec)
        flasher.flash_message(f"Deleted plot '{spec.name}'.", FlashTypes.SUCCESS)
        DB.session.commit()
        return redirect(url_for(".index"))

    return blueprint
