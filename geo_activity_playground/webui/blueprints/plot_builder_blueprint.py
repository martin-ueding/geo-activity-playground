import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for

from ...core.activities import ActivityRepository
from ...core.datamodel import DB
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
    def index() -> Response:
        return render_template(
            "plot_builder/index.html.j2",
            specs=DB.session.scalars(sqlalchemy.select(PlotSpec)).all(),
        )

    @blueprint.route("/new")
    @needs_authentication(authenticator)
    def new() -> Response:
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

    @blueprint.route("/edit/<int:id>")
    @needs_authentication(authenticator)
    def edit(id: int) -> Response:
        spec = DB.session.get(PlotSpec, id)
        if request.args:
            spec.name = request.args["name"]
            spec.mark = request.args["mark"]
            spec.x = request.args["x"]
            spec.y = request.args["y"]
            spec.color = request.args["color"]
            spec.shape = request.args["shape"]
            spec.size = request.args["size"]
            spec.size = request.args["size"]
            spec.row = request.args["row"]
            spec.column = request.args["column"]
            spec.facet = request.args["facet"]
            spec.opacity = request.args["opacity"]
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
            plot=plot,
            spec=spec,
        )

    @blueprint.route("/delete/<int:id>")
    @needs_authentication(authenticator)
    def delete(id: int) -> Response:
        spec = DB.session.get(PlotSpec, id)
        DB.session.delete(spec)
        flasher.flash_message(f"Deleted plot '{spec.name}'.", FlashTypes.SUCCESS)
        DB.session.commit()
        return redirect(url_for(".index"))

    return blueprint
