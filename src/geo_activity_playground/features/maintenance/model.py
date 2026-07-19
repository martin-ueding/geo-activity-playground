import datetime
import decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Equipment


class MaintenanceAction(DB.Model):
    __tablename__ = "maintenance_actions"
    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(sa.String, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    date: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    usage_km: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    cost: Mapped[decimal.Decimal | None] = mapped_column(
        sa.Numeric(10, 2), nullable=True
    )

    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="equipment_id"), nullable=False
    )
    equipment: Mapped["Equipment"] = relationship(back_populates="maintenance_actions")

    photos: Mapped[list["MaintenanceActionPhoto"]] = relationship(
        back_populates="maintenance_action", cascade="all, delete-orphan"
    )


class MaintenanceActionPhoto(DB.Model):
    __tablename__ = "maintenance_action_photos"
    id: Mapped[int] = mapped_column(primary_key=True)

    caption: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    filename: Mapped[str] = mapped_column(sa.String, nullable=False)

    maintenance_action_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_actions.id", name="maintenance_action_id"),
        nullable=False,
    )
    maintenance_action: Mapped["MaintenanceAction"] = relationship(
        back_populates="photos"
    )


class RecurringTask(DB.Model):
    __tablename__ = "recurring_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(sa.String, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    interval_days: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    interval_km: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="equipment_id"), nullable=False
    )
    equipment: Mapped["Equipment"] = relationship(back_populates="recurring_tasks")

    executions: Mapped[list["TaskExecution"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskExecution(DB.Model):
    __tablename__ = "task_executions"
    id: Mapped[int] = mapped_column(primary_key=True)

    comment: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    date: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    usage_km: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_tasks.id", name="task_id"), nullable=False
    )
    task: Mapped["RecurringTask"] = relationship(back_populates="executions")
