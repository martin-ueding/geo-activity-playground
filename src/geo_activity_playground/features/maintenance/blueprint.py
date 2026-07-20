import datetime
import decimal

import altair as alt
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
from .stats import get_cost_by_equipment, get_maintenance_actions_table


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


def _maintenance_plots(actions: pd.DataFrame, summary: pd.DataFrame) -> dict[str, str]:
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
        alt.Chart(summary, height=300, title=_("Cost vs. usage"))
        .mark_point()
        .encode(
            alt.X("total_distance_km", title=_("Total usage / km")),
            alt.Y("total_cost", title=_("Total cost")),
            alt.Color("equipment", title=_("Equipment")),
            tooltip=[
                alt.Tooltip("equipment:N", title=_("Equipment")),
                alt.Tooltip("total_distance_km:Q", title=_("Total usage / km")),
                alt.Tooltip("total_cost:Q", title=_("Total cost"), format=".2f"),
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
        if has_cost_data:
            variables["plots"] = _maintenance_plots(actions, summary)
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
