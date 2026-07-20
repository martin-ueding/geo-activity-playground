import altair as alt
import numpy as np
import pandas as pd
import sqlalchemy
from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Equipment
from ...core.internal_pictures import delete_internal_picture, save_internal_picture
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from ...webui.plot_util import make_kind_scale
from ..maintenance.stats import (
    get_maintenance_actions_table,
    get_maintenance_flow_by_title,
)
from .stats import get_equipment_use_table


def _stack_nodes(
    order: list[str], totals: pd.Series, gap: float
) -> dict[str, tuple[float, float]]:
    positions = {}
    y = 0.0
    for name in order:
        positions[name] = (y, y + totals[name])
        y += totals[name] + gap
    return positions


def _maintenance_flow_plot(links: pd.DataFrame) -> str | None:
    if links.empty:
        return None

    equipment_totals = links.groupby("equipment")["cost"].sum()
    title_totals = links.groupby("title")["cost"].sum()
    equipment_order = list(equipment_totals.sort_values(ascending=False).index)
    title_order = list(title_totals.sort_values(ascending=False).index)

    gap = links["cost"].sum() * 0.02
    equipment_pos = _stack_nodes(equipment_order, equipment_totals, gap)
    title_pos = _stack_nodes(title_order, title_totals, gap)

    links_sorted = links.copy()
    links_sorted["equipment"] = pd.Categorical(
        links_sorted["equipment"], categories=equipment_order, ordered=True
    )
    links_sorted["title"] = pd.Categorical(
        links_sorted["title"], categories=title_order, ordered=True
    )
    links_sorted = links_sorted.sort_values(["equipment", "title"])

    left_cursor = {name: pos[0] for name, pos in equipment_pos.items()}
    right_cursor = {name: pos[0] for name, pos in title_pos.items()}

    num_steps = 20
    t = np.linspace(0.0, 1.0, num_steps)
    smoothstep = 3 * t**2 - 2 * t**3

    curve_rows = []
    for link_id, (equipment, title, cost) in enumerate(
        zip(
            links_sorted["equipment"].astype(str),
            links_sorted["title"].astype(str),
            links_sorted["cost"],
        )
    ):
        y0_left = left_cursor[equipment]
        y1_left = y0_left + cost
        left_cursor[equipment] = y1_left
        y0_right = right_cursor[title]
        y1_right = y0_right + cost
        right_cursor[title] = y1_right

        top = y0_left + (y0_right - y0_left) * smoothstep
        bottom = y1_left + (y1_right - y1_left) * smoothstep
        for x, y, y2 in zip(t, top, bottom):
            curve_rows.append(
                {
                    "link_id": link_id,
                    "x": x,
                    "y": y,
                    "y2": y2,
                    "equipment": equipment,
                    "title": title,
                    "cost": cost,
                }
            )
    curve_df = pd.DataFrame(curve_rows)

    node_width = 0.02
    node_rows = []
    for name in equipment_order:
        y0, y1 = equipment_pos[name]
        node_rows.append(
            {
                "x0": -node_width,
                "x1": 0.0,
                "y0": y0,
                "y1": y1,
                "label": name,
                "total": equipment_totals[name],
                "side": "equipment",
            }
        )
    for name in title_order:
        y0, y1 = title_pos[name]
        node_rows.append(
            {
                "x0": 1.0,
                "x1": 1.0 + node_width,
                "y0": y0,
                "y1": y1,
                "label": name,
                "total": title_totals[name],
                "side": "title",
            }
        )
    node_df = pd.DataFrame(node_rows)
    equipment_nodes = node_df[node_df["side"] == "equipment"]
    title_nodes = node_df[node_df["side"] == "title"]

    x_scale = alt.Scale(domain=[-0.5, 1.5])
    y_scale = alt.Scale(domain=[curve_df[["y", "y2"]].values.max(), 0])

    links_chart = (
        alt.Chart(curve_df)
        .mark_area(opacity=0.4, interpolate="monotone")
        .encode(
            x=alt.X("x:Q", axis=None, scale=x_scale),
            y=alt.Y("y:Q", axis=None, scale=y_scale),
            y2="y2:Q",
            color=alt.Color("equipment:N", legend=None),
            detail="link_id:N",
            tooltip=[
                alt.Tooltip("equipment:N", title=_("Equipment")),
                alt.Tooltip("title:N", title=_("Title")),
                alt.Tooltip("cost:Q", title=_("Cost"), format=".2f"),
            ],
        )
    )
    equipment_rects = (
        alt.Chart(equipment_nodes)
        .mark_rect()
        .encode(
            x=alt.X("x0:Q", axis=None, scale=x_scale),
            x2="x1:Q",
            y=alt.Y("y0:Q", axis=None, scale=y_scale),
            y2="y1:Q",
            color=alt.Color("label:N", legend=None),
            tooltip=[
                alt.Tooltip("label:N", title=_("Equipment")),
                alt.Tooltip("total:Q", title=_("Cost"), format=".2f"),
            ],
        )
    )
    title_rects = (
        alt.Chart(title_nodes)
        .mark_rect(color="#888888")
        .encode(
            x=alt.X("x0:Q", axis=None, scale=x_scale),
            x2="x1:Q",
            y=alt.Y("y0:Q", axis=None, scale=y_scale),
            y2="y1:Q",
            tooltip=[
                alt.Tooltip("label:N", title=_("Title")),
                alt.Tooltip("total:Q", title=_("Cost"), format=".2f"),
            ],
        )
    )
    equipment_text = (
        alt.Chart(equipment_nodes)
        .mark_text(align="right", dx=-6)
        .encode(
            x=alt.X("x0:Q", scale=x_scale),
            y=alt.Y("y_mid:Q", scale=y_scale),
            text="label:N",
        )
        .transform_calculate(y_mid="(datum.y0 + datum.y1) / 2")
    )
    title_text = (
        alt.Chart(title_nodes)
        .mark_text(align="left", dx=6)
        .encode(
            x=alt.X("x1:Q", scale=x_scale),
            y=alt.Y("y_mid:Q", scale=y_scale),
            text="label:N",
        )
        .transform_calculate(y_mid="(datum.y0 + datum.y1) / 2")
    )

    chart = (
        alt.layer(links_chart, equipment_rects, title_rects, equipment_text, title_text)
        .properties(
            width=700,
            height=max(300, 24 * max(len(equipment_order), len(title_order))),
            title=_("Maintenance cost flow"),
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False, domain=False, ticks=False, labels=False)
    )
    return chart.to_json(format="vega")


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


def _apply_uploaded_picture(equipment: Equipment, flasher: Flasher) -> None:
    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        return
    try:
        new_filename = save_internal_picture(image_file)
    except ValueError as e:
        flasher.flash_message(str(e), FlashTypes.WARNING)
        return
    if equipment.picture_filename:
        delete_internal_picture(equipment.picture_filename)
    equipment.picture_filename = new_filename


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
        equipment_picture_filenames = {
            equipment.name: equipment.picture_filename for equipment in equipments
        }
        offsets = {equipment.name: equipment.offset_km for equipment in equipments}
        equipment_summary = get_equipment_use_table(repository.meta, offsets)
        equipment_summary["id"] = equipment_summary["equipment"].map(equipment_ids)
        # dtype=object avoids pandas coercing missing filenames to float NaN
        # (truthy in Jinja) instead of None, which .map() would otherwise do.
        equipment_summary["picture_filename"] = pd.Series(
            [
                equipment_picture_filenames.get(name)
                for name in equipment_summary["equipment"]
            ],
            dtype=object,
            index=equipment_summary.index,
        )

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
            .interactive(bind_y=False)
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
        usage_km = round(equipment.total_distance_km)

        actions = get_maintenance_actions_table()
        equipment_actions = actions.loc[actions["equipment"] == equipment.name]
        flow_plot = (
            _maintenance_flow_plot(get_maintenance_flow_by_title(equipment_actions))
            if len(equipment_actions)
            else None
        )

        variables = {
            "equipment": equipment,
            "usage_km": usage_km,
            "plots": _equipment_plots(repository, config_accessor, equipment.name),
            "flow_plot": flow_plot,
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
            _apply_uploaded_picture(equipment, flasher)
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
            _apply_uploaded_picture(equipment, flasher)
            DB.session.add(equipment)
            DB.session.commit()
            flasher.flash_message(
                _("Equipment '%(name)s' added.", name=equipment.name),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for(".show", id=equipment.id))
        return render_template("equipment/edit.html.j2", equipment=None)

    return blueprint
