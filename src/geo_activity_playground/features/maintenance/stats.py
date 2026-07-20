import pandas as pd
import sqlalchemy as sa

from ...core.datamodel import DB, Equipment
from .model import MaintenanceAction, RecurringTask


def get_maintenance_actions_table() -> pd.DataFrame:
    rows = DB.session.execute(
        sa.select(
            MaintenanceAction.id,
            MaintenanceAction.title,
            MaintenanceAction.date,
            MaintenanceAction.usage_km,
            MaintenanceAction.cost,
            Equipment.name.label("equipment"),
        ).join(MaintenanceAction.equipment)
    ).all()
    df = pd.DataFrame(
        rows, columns=["id", "title", "date", "usage_km", "cost", "equipment"]
    )
    if len(df):
        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["cost"] = df["cost"].astype(float)
    return df


def get_cost_by_equipment(actions: pd.DataFrame) -> pd.DataFrame:
    summary = (
        actions.groupby("equipment")
        .agg(total_cost=("cost", "sum"), num_actions=("id", "count"))
        .reset_index()
        .sort_values("total_cost", ascending=False)
    )
    equipments = DB.session.scalars(sa.select(Equipment)).all()
    usage = pd.DataFrame(
        {
            "equipment": equipment.name,
            "total_distance_km": equipment.total_distance_km,
        }
        for equipment in equipments
    )
    return summary.merge(usage, on="equipment", how="left")


def get_maintenance_flow_by_title(actions: pd.DataFrame) -> pd.DataFrame:
    return (
        actions.groupby(["equipment", "title"])["cost"].sum().reset_index(name="cost")
    )


def get_due_tasks() -> list[RecurringTask]:
    tasks = DB.session.scalars(sa.select(RecurringTask)).all()
    due = [task for task in tasks if task.is_overdue(task.equipment.total_distance_km)]
    return sorted(due, key=lambda task: (task.equipment.name, task.title))
