import datetime
import decimal

import altair as alt
import numpy as np
import pandas as pd
from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.datamodel import DB, Equipment
from ...core.internal_pictures import delete_internal_picture, save_internal_picture
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from .model import (
    MaintenanceAction,
    MaintenanceActionPhoto,
    RecurringTask,
    TaskExecution,
)
from .stats import (
    get_cost_by_equipment,
    get_maintenance_actions_table,
    get_maintenance_flow_by_title,
)


def _parse_int(value: str | None) -> int | None:
    return int(float(value)) if value else None


def _parse_decimal(value: str | None) -> decimal.Decimal | None:
    return decimal.Decimal(value) if value else None


def _parse_date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


def _apply_uploaded_photos(action: MaintenanceAction) -> None:
    for image_file in request.files.getlist("photos"):
        if not image_file or not image_file.filename:
            continue
        filename = save_internal_picture(image_file)
        DB.session.add(
            MaintenanceActionPhoto(maintenance_action=action, filename=filename)
        )


def _maintenance_plots(actions: pd.DataFrame) -> dict[str, str]:
    cost_by_equipment_plot = (
        alt.Chart(actions, height=300, title=_("Cost by equipment"))
        .mark_bar()
        .encode(
            alt.X("sum(cost)", title=_("Cost")),
            alt.Y("equipment", sort="-x", title=_("Equipment")),
            tooltip=[
                alt.Tooltip("equipment:N", title=_("Equipment")),
                alt.Tooltip("sum(cost):Q", title=_("Cost"), format=".2f"),
            ],
        )
        .to_json(format="vega")
    )

    cost_by_year_plot = (
        alt.Chart(actions, height=300, title=_("Cost by year"))
        .mark_bar()
        .encode(
            alt.X("year:O", title=_("Year")),
            alt.Y("sum(cost)", title=_("Cost")),
            alt.Color("equipment", title=_("Equipment")),
            tooltip=[
                alt.Tooltip("year:O", title=_("Year")),
                alt.Tooltip("equipment:N", title=_("Equipment")),
                alt.Tooltip("sum(cost):Q", title=_("Cost"), format=".2f"),
            ],
        )
        .to_json(format="vega")
    )

    cost_vs_usage_plot = (
        alt.Chart(actions, height=300, title=_("Cost vs. usage"))
        .mark_point()
        .encode(
            alt.X("usage_km", title=_("Usage / km")),
            alt.Y("cost", title=_("Cost")),
            alt.Color("equipment", title=_("Equipment")),
            tooltip=[
                alt.Tooltip("title:N", title=_("Title")),
                alt.Tooltip("equipment:N", title=_("Equipment")),
                alt.Tooltip("usage_km:Q", title=_("Usage / km")),
                alt.Tooltip("cost:Q", title=_("Cost"), format=".2f"),
            ],
        )
        .interactive()
        .to_json(format="vega")
    )

    return {
        "cost_by_equipment_plot": cost_by_equipment_plot,
        "cost_by_year_plot": cost_by_year_plot,
        "cost_vs_usage_plot": cost_vs_usage_plot,
    }


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

    equipment_totals = links.groupby("equipment")["count"].sum()
    title_totals = links.groupby("title")["count"].sum()
    equipment_order = list(equipment_totals.sort_values(ascending=False).index)
    title_order = list(title_totals.sort_values(ascending=False).index)

    gap = links["count"].sum() * 0.02
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
    for link_id, (equipment, title, count) in enumerate(
        zip(
            links_sorted["equipment"].astype(str),
            links_sorted["title"].astype(str),
            links_sorted["count"],
        )
    ):
        y0_left = left_cursor[equipment]
        y1_left = y0_left + count
        left_cursor[equipment] = y1_left
        y0_right = right_cursor[title]
        y1_right = y0_right + count
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
                    "count": count,
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
                alt.Tooltip("count:Q", title=_("Number of actions")),
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
                alt.Tooltip("total:Q", title=_("Number of actions")),
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
                alt.Tooltip("total:Q", title=_("Number of actions")),
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
            title=_("Bike to maintenance flow"),
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False, domain=False, ticks=False, labels=False)
    )
    return chart.to_json(format="vega")


def make_maintenance_blueprint(
    authenticator: Authenticator, flasher: Flasher
) -> Blueprint:
    blueprint = Blueprint("maintenance", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        actions = get_maintenance_actions_table()
        has_cost_data = len(actions) > 0 and actions["cost"].notna().any()

        variables = {
            "has_actions": len(actions) > 0,
            "has_cost_data": has_cost_data,
        }
        if len(actions):
            summary = get_cost_by_equipment(actions)
            variables["summary"] = summary.to_dict(orient="records")
            variables["total_cost"] = float(actions["cost"].sum(skipna=True))
            variables["flow_plot"] = _maintenance_flow_plot(
                get_maintenance_flow_by_title(actions)
            )
        if has_cost_data:
            variables["plots"] = _maintenance_plots(actions)
        return render_template("maintenance/index.html.j2", **variables)

    @blueprint.route(
        "/equipment/<int:equipment_id>/actions/new", methods=["GET", "POST"]
    )
    @needs_authentication(authenticator)
    def new_action(equipment_id: int) -> ResponseReturnValue:
        equipment = DB.session.get_one(Equipment, equipment_id)
        if request.method == "POST":
            action = MaintenanceAction(
                equipment=equipment,
                title=request.form["title"],
                description=request.form.get("description") or None,
                date=_parse_date(request.form["date"]),
                usage_km=_parse_int(request.form.get("usage_km")),
                cost=_parse_decimal(request.form.get("cost")),
            )
            DB.session.add(action)
            DB.session.flush()
            _apply_uploaded_photos(action)
            DB.session.commit()
            flasher.flash_message(
                _("Maintenance action '%(title)s' added.", title=action.title),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for("equipment.show", id=equipment_id))
        defaults = {
            "date": datetime.date.today(),
            "usage_km": round(equipment.total_distance_km),
        }
        return render_template(
            "maintenance/action_edit.html.j2",
            equipment=equipment,
            action=None,
            defaults=defaults,
        )

    @blueprint.route("/actions/<int:id>/edit", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def edit_action(id: int) -> ResponseReturnValue:
        action = DB.session.get_one(MaintenanceAction, id)
        if request.method == "POST":
            action.title = request.form["title"]
            action.description = request.form.get("description") or None
            action.date = _parse_date(request.form["date"])
            action.usage_km = _parse_int(request.form.get("usage_km"))
            action.cost = _parse_decimal(request.form.get("cost"))
            _apply_uploaded_photos(action)
            DB.session.commit()
            flasher.flash_message(
                _("Maintenance action '%(title)s' updated.", title=action.title),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for("equipment.show", id=action.equipment_id))
        return render_template(
            "maintenance/action_edit.html.j2",
            equipment=action.equipment,
            action=action,
            defaults=None,
        )

    @blueprint.route("/actions/<int:id>/delete")
    @needs_authentication(authenticator)
    def delete_action(id: int) -> ResponseReturnValue:
        action = DB.session.get_one(MaintenanceAction, id)
        equipment_id = action.equipment_id
        for photo in action.photos:
            delete_internal_picture(photo.filename)
        DB.session.delete(action)
        DB.session.commit()
        flasher.flash_message(_("Maintenance action deleted."), FlashTypes.SUCCESS)
        return redirect(url_for("equipment.show", id=equipment_id))

    @blueprint.route("/action-photos/<int:id>/delete")
    @needs_authentication(authenticator)
    def delete_action_photo(id: int) -> ResponseReturnValue:
        photo = DB.session.get_one(MaintenanceActionPhoto, id)
        action_id = photo.maintenance_action_id
        delete_internal_picture(photo.filename)
        DB.session.delete(photo)
        DB.session.commit()
        return redirect(url_for(".edit_action", id=action_id))

    @blueprint.route("/equipment/<int:equipment_id>/tasks/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def new_task(equipment_id: int) -> ResponseReturnValue:
        equipment = DB.session.get_one(Equipment, equipment_id)
        if request.method == "POST":
            task = RecurringTask(
                equipment=equipment,
                title=request.form["title"],
                description=request.form.get("description") or None,
                interval_days=_parse_int(request.form.get("interval_days")),
                interval_km=_parse_int(request.form.get("interval_km")),
            )
            DB.session.add(task)
            DB.session.commit()
            flasher.flash_message(
                _("Recurring task '%(title)s' added.", title=task.title),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for("equipment.show", id=equipment_id))
        return render_template(
            "maintenance/task_edit.html.j2", equipment=equipment, task=None
        )

    @blueprint.route("/tasks/<int:id>/edit", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def edit_task(id: int) -> ResponseReturnValue:
        task = DB.session.get_one(RecurringTask, id)
        if request.method == "POST":
            task.title = request.form["title"]
            task.description = request.form.get("description") or None
            task.interval_days = _parse_int(request.form.get("interval_days"))
            task.interval_km = _parse_int(request.form.get("interval_km"))
            DB.session.commit()
            flasher.flash_message(
                _("Recurring task '%(title)s' updated.", title=task.title),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for("equipment.show", id=task.equipment_id))
        return render_template(
            "maintenance/task_edit.html.j2", equipment=task.equipment, task=task
        )

    @blueprint.route("/tasks/<int:id>/delete")
    @needs_authentication(authenticator)
    def delete_task(id: int) -> ResponseReturnValue:
        task = DB.session.get_one(RecurringTask, id)
        equipment_id = task.equipment_id
        DB.session.delete(task)
        DB.session.commit()
        flasher.flash_message(_("Recurring task deleted."), FlashTypes.SUCCESS)
        return redirect(url_for("equipment.show", id=equipment_id))

    @blueprint.route("/tasks/<int:id>/execute", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def execute_task(id: int) -> ResponseReturnValue:
        task = DB.session.get_one(RecurringTask, id)
        if request.method == "POST":
            execution = TaskExecution(
                task=task,
                date=_parse_date(request.form["date"]),
                usage_km=_parse_int(request.form.get("usage_km")),
                comment=request.form.get("comment") or None,
            )
            DB.session.add(execution)
            DB.session.commit()
            flasher.flash_message(
                _("Task '%(title)s' marked as done.", title=task.title),
                FlashTypes.SUCCESS,
            )
            return redirect(url_for("equipment.show", id=task.equipment_id))
        defaults = {
            "date": datetime.date.today(),
            "usage_km": round(task.equipment.total_distance_km),
        }
        return render_template(
            "maintenance/task_execution_new.html.j2", task=task, defaults=defaults
        )

    @blueprint.route("/executions/<int:id>/delete")
    @needs_authentication(authenticator)
    def delete_execution(id: int) -> ResponseReturnValue:
        execution = DB.session.get_one(TaskExecution, id)
        equipment_id = execution.task.equipment_id
        DB.session.delete(execution)
        DB.session.commit()
        flasher.flash_message(_("Task execution deleted."), FlashTypes.SUCCESS)
        return redirect(url_for("equipment.show", id=equipment_id))

    return blueprint
