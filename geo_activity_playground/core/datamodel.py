import datetime
import logging
from typing import Any
from typing import TypedDict

import numpy as np
import pandas as pd
import sqlalchemy
import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from .config import Config
from .paths import time_series_dir


logger = logging.getLogger(__name__)


class ActivityMeta(TypedDict):
    average_speed_elapsed_kmh: float
    average_speed_moving_kmh: float
    calories: float
    commute: bool
    consider_for_achievements: bool
    distance_km: float
    elapsed_time: datetime.timedelta
    elevation_gain: float
    end_latitude: float
    end_longitude: float
    equipment: str
    id: int
    kind: str
    moving_time: datetime.timedelta
    name: str
    path: str
    start_latitude: float
    start_longitude: float
    start: np.datetime64
    steps: int


class Base(DeclarativeBase):
    pass


DB = SQLAlchemy(model_class=Base)


class Activity(DB.Model):
    __tablename__ = "activities"

    # Housekeeping data:
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    distance_km: Mapped[float] = mapped_column(sa.Float, nullable=False)

    # Where it comes from:
    path: Mapped[str] = mapped_column(sa.String, nullable=True)
    upstream_id: Mapped[str] = mapped_column(sa.String, nullable=True)

    # Crop data:
    index_begin: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    index_end: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # Temporal data:
    start: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=True)
    elapsed_time: Mapped[datetime.timedelta] = mapped_column(sa.Interval, nullable=True)
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
    num_new_tiles_14: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    num_new_tiles_17: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    # References to other tables:
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", name="equipment_id"), nullable=True
    )
    equipment: Mapped["Equipment"] = relationship(back_populates="activities")
    kind_id: Mapped[int] = mapped_column(
        ForeignKey("kinds.id", name="kind_id"), nullable=True
    )
    kind: Mapped["Kind"] = relationship(back_populates="activities")

    def __getitem__(self, item) -> Any:
        return self.to_dict()[item]

    def __str__(self) -> str:
        return f"{self.start} {self.name}"

    @property
    def average_speed_moving_kmh(self) -> float:
        return self.distance_km / (self.moving_time.total_seconds() / 3_600)

    @property
    def average_speed_elapsed_kmh(self) -> float:
        return self.distance_km / (self.elapsed_time.total_seconds() / 3_600)

    @property
    def raw_time_series(self) -> pd.DataFrame:
        path = time_series_dir() / f"{self.id}.parquet"
        try:
            return pd.read_parquet(path)
        except OSError as e:
            logger.error(f"Error while reading {path}, deleting cache file …")
            path.unlink(missing_ok=True)
            raise

    @property
    def time_series(self) -> pd.DataFrame:
        if self.index_begin or self.index_end:
            return self.raw_time_series.iloc[
                self.index_begin or 0 : self.index_end or -1
            ]
        else:
            return self.raw_time_series

    def to_dict(self) -> ActivityMeta:
        equipment = self.equipment.name if self.equipment is not None else "Unknown"
        kind = self.kind.name if self.kind is not None else "Unknown"
        consider_for_achievements = (
            self.kind.consider_for_achievements if self.kind is not None else True
        )
        return ActivityMeta(
            id=self.id,
            name=self.name,
            path=self.path,
            distance_km=self.distance_km,
            start=self.start,
            elapsed_time=self.elapsed_time,
            moving_time=self.moving_time,
            start_latitude=self.start_latitude,
            start_longitude=self.start_longitude,
            end_latitude=self.end_latitude,
            end_longitude=self.end_longitude,
            elevation_gain=self.elevation_gain,
            start_elevation=self.start_elevation,
            end_elevation=self.end_elevation,
            calories=self.calories,
            steps=self.steps,
            num_new_tiles_14=self.num_new_tiles_14,
            num_new_tiles_17=self.num_new_tiles_17,
            equipment=equipment,
            kind=kind,
            average_speed_moving_kmh=self.average_speed_moving_kmh,
            average_speed_elapsed_kmh=self.average_speed_elapsed_kmh,
            consider_for_achievements=consider_for_achievements,
        )


class Equipment(DB.Model):
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

    def __str__(self) -> str:
        return f"{self.name} ({self.offset_km} km)"

    __table_args__ = (sa.UniqueConstraint("name", name="equipments_name"),)


class Kind(DB.Model):
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
        ForeignKey("equipments.id", name="default_equipment_id"), nullable=True
    )
    default_equipment: Mapped["Equipment"] = relationship(
        back_populates="default_for_kinds"
    )

    __table_args__ = (sa.UniqueConstraint("name", name="kinds_name"),)


class SquarePlannerBookmark(DB.Model):
    __tablename__ = "square_planner_bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)

    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    __table_args__ = (sa.UniqueConstraint("zoom", "x", "y", "size", name="kinds_name"),)


def get_or_make_kind(name: str, config: Config) -> Kind:
    kinds = DB.session.scalars(sqlalchemy.select(Kind).where(Kind.name == name)).all()
    if kinds:
        assert len(kinds) == 1, f"There must be only one kind with name '{name}'."
        return kinds[0]
    else:
        kind = Kind(
            name=name,
            consider_for_achievements=config.kinds_without_achievements.get(name, True),
        )
        DB.session.add(kind)
        return kind


def get_or_make_equipment(name: str, config: Config) -> Equipment:
    equipments = DB.session.scalars(
        sqlalchemy.select(Equipment).where(Equipment.name == name)
    ).all()
    if equipments:
        assert (
            len(equipments) == 1
        ), f"There must be only one equipment with name '{name}'."
        return equipments[0]
    else:
        equipment = Equipment(
            name=name, offset_km=config.equipment_offsets.get(name, 0)
        )
        DB.session.add(equipment)
        return equipment
