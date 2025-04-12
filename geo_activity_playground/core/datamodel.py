import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class Activity(Base):
    __tablename__ = "activities"

    # Housekeeping data:
    id: Mapped[int] = mapped_column(primary_key=True)
    updated: Mapped[datetime.timedelta] = mapped_column(sa.DateTime, nullable=False)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    path: Mapped[str] = mapped_column(sa.String, nullable=True)

    distance_km: Mapped[float] = mapped_column(sa.Float, nullable=False)

    # Temporal data:
    start: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    elapsed_time: Mapped[datetime.timedelta] = mapped_column(
        sa.Interval, nullable=False
    )
    moving_time: Mapped[datetime.timedelta] = mapped_column(sa.Interval, nullable=True)

    # Geographic data:
    start_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)

    # Elevation data:
    elevation_gain: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_elevation: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_elevation: Mapped[float] = mapped_column(sa.Float, nullable=True)

    # Health data:
    calories: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    steps: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # Tile achievements:
    num_new_tiles_14: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    num_new_tiles_17: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # References to other tables:
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="equipment_id")
    )
    equipment: Mapped["Equipment"] = relationship(back_populates="activities")
    kind_id: Mapped[int] = mapped_column(ForeignKey("kinds.id", name="kind_id"))
    kind: Mapped["Kind"] = relationship(back_populates="activities")


class Equipment(Base):
    __tablename__ = "equipments"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)
    offset_km: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )
    default_for_kinds: Mapped[list["Kind"]] = relationship(
        back_populates="default_equipment", cascade="all, delete-orphan"
    )

    __table_args__ = (sa.UniqueConstraint("name", name="equipments_name"),)


class Kind(Base):
    __tablename__ = "kinds"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)
    consider_for_achievements: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, nullable=False
    )

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="kind", cascade="all, delete-orphan"
    )
    default_equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="default_equipment_id")
    )
    default_equipment: Mapped["Equipment"] = relationship(back_populates="kinds")

    __table_args__ = (sa.UniqueConstraint("name", name="kinds_name"),)
