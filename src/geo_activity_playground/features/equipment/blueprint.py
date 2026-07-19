import altair as alt
import pandas as pd
import sqlalchemy
from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Equipment
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from ...webui.plot_util import make_kind_scale
from .stats import get_equipment_use_table


def _equipment_plots(
    repository: ActivityRepository, config_accessor: ConfigAccessor, equipment: str
) -> dict[str, str]:
    selection = repository.meta.loc[repository.meta["equipment"] == equipment]
    total_distances = pd.DataFrame(
        {
            "time": selection["start_local"],
            "total_distance_km": selection["distance_km"].cumsum(),
        }
    )

    total_distances_plot = (
        alt.Chart(
            total_distances,
            height=300,
            width=300,
            title=_("Usage over Time"),
        )
        .mark_line(interpolate="step-after")
        .encode(
            alt.X("time", title=_("Date")),
            alt.Y("total_distance_km", title=_("Cumulative distance / km")),
            tooltip=[
                alt.Tooltip("time:T", title=_("Date")),
                alt.Tooltip(
                    "total_distance_km:Q",
                    title=_("Cumulative distance / km"),
                    format=".0f",
                ),
            ],
        )
        .interactive()
        .to_json(format="vega")
    )

    yearly_distance_plot = (
        alt.Chart(
            selection,
            height=300,
            title=_("Yearly distance"),
        )
        .mark_bar()
        .encode(
            alt.X("year(start_local):O", title=_("Year")),
            alt.Y("sum(distance_km)", title=_("Distance / km")),
            alt.Color(
                "kind",
                scale=make_kind_scale(repository.meta, config_accessor.ui()),
                title=_("Kind"),
            ),
            tooltip=[
                alt.Tooltip("year(start_local):O", title=_("Year")),
                alt.Tooltip(
                    "sum(distance_km):Q", title=_("Distance / km"), format=".0f"
                ),
                alt.Tooltip("kind:N", title=_("Kind")),
            ],
        )
        .to_json(format="vega")
    )

    usages_plot = (
        alt.Chart(
            selection,
            height=300,
            title=_("Kinds"),
        )
        .mark_bar()
        .encode(
            alt.X(
                "kind",
                title=_("Kind"),
            ),
            alt.Y("sum(distance_km)", title=_("Distance / km")),
            tooltip=[
                alt.Tooltip("kind:N", title=_("Kind")),
                alt.Tooltip(
                    "sum(distance_km):Q", title=_("Distance / km"), format=".0f"
                ),
            ],
        )
        .to_json(format="vega")
    )

    return {
        "total_distances_plot": total_distances_plot,
        "yearly_distance_plot": yearly_distance_plot,
        "usages_plot": usages_plot,
    }


def make_equipment_blueprint(
    repository: ActivityRepository,
    config_accessor: ConfigAccessor,
    authenticator: Authenticator,
    flasher: Flasher,
) -> Blueprint:
    blueprint = Blueprint("equipment", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        equipments = DB.session.scalars(sqlalchemy.select(Equipment)).all()
        equipment_ids = {equipment.name: equipment.id for equipment in equipments}
        offsets = {equipment.name: equipment.offset_km for equipment in equipments}
        equipment_summary = get_equipment_use_table(repository.meta, offsets)
        equipment_summary["id"] = equipment_summary["equipment"].map(equipment_ids)

        # Prepare data for the stacked area chart
        activities = repository.meta.dropna(subset=["start_local"])
        activities["month"] = (
            activities["start_local"].dt.to_period("M").apply(lambda r: r.start_time)
        )
        monthly_data = (
            activities.groupby(["month", "equipment"])
            .agg(total_distance=("distance_km", "sum"))
            .reset_index()
        )

        stacked_area_chart = (
            alt.Chart(
                monthly_data, height=300, width=1200, title=_("Monthly Equipment Usage")
            )
            .mark_area()
            .encode(
                x=alt.X("month:T", title=_("Month")),
                y=alt.Y("total_distance:Q", title=_("Total Kilometers per Month")),
                color=alt.Color("equipment:N", title=_("Equipment")),
                tooltip=[
                    alt.Tooltip("month:T", title=_("Date")),
                    alt.Tooltip("equipment:N", title=_("Equipment")),
                    alt.Tooltip(
                        "total_distance:Q", format=".0f", title=_("Total Distance")
                    ),
                ],
            )
            .interactive()
            .to_json(format="vega")
        )

        variables = {
            "equipment_summary": equipment_summary.to_dict(orient="records"),
            "stacked_area_chart": stacked_area_chart,
            "is_authenticated": authenticator.is_authenticated(),
        }

        return render_template("equipment/index.html.j2", **variables)

    @blueprint.route("/<int:id>")
    def show(id: int) -> ResponseReturnValue:
        equipment = DB.session.get_one(Equipment, id)
        offsets = {equipment.name: equipment.offset_km}
        equipment_summary = get_equipment_use_table(repository.meta, offsets)
        row = equipment_summary.loc[equipment_summary["equipment"] == equipment.name]
        usage_km = (
            int(row["total_distance_km"].iloc[0]) if len(row) else equipment.offset_km
        )

        variables = {
            "equipment": equipment,
            "usage_km": usage_km,
            "plots": _equipment_plots(repository, config_accessor, equipment.name),
            "is_authenticated": authenticator.is_authenticated(),
        }
        return render_template("equipment/show.html.j2", **variables)

    @blueprint.route("/<int:id>/edit", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def edit(id: int) -> ResponseReturnValue:
        equipment = DB.session.get_one(Equipment, id)
        if request.method == "POST":
            equipment.name = request.form["name"]
            equipment.offset_km = int(float(request.form["offset_km"]))
            DB.session.commit()
            flasher.flash_message(
                _("Equipment '%(name)s' updated.", name=equipment.name),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for(".show", id=equipment.id))
        return render_template("equipment/edit.html.j2", equipment=equipment)

    @blueprint.route("/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def new() -> ResponseReturnValue:
        if request.method == "POST":
            equipment = Equipment(name=request.form["name"])
            offset_km = request.form.get("offset_km", "")
            if offset_km:
                equipment.offset_km = int(float(offset_km))
            DB.session.add(equipment)
            DB.session.commit()
            flasher.flash_message(
                _("Equipment '%(name)s' added.", name=equipment.name),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for(".show", id=equipment.id))
        return render_template("equipment/edit.html.j2", equipment=None)

    return blueprint
