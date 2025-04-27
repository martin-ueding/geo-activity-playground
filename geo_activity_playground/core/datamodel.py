import datetime
import json
import logging
import pathlib
from typing import Any
from typing import Optional
from typing import TypedDict

import numpy as np
import pandas as pd
import sqlalchemy
import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Table
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

activity_tag_association_table = Table(
    "activity_tag_association_table",
    Base.metadata,
    Column("left_id", ForeignKey("activities.id"), primary_key=True),
    Column("right_id", ForeignKey("tags.id"), primary_key=True),
)


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

    tags: Mapped[list["Tag"]] = relationship(
        secondary=activity_tag_association_table, back_populates="activities"
    )

    photos: Mapped[list["Photo"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.start} {self.name}"

    @property
    def average_speed_moving_kmh(self) -> Optional[float]:
        if self.moving_time:
            return self.distance_km / (self.moving_time.total_seconds() / 3_600)
        else:
            return None

    @property
    def average_speed_elapsed_kmh(self) -> Optional[float]:
        if self.elapsed_time:
            return self.distance_km / (self.elapsed_time.total_seconds() / 3_600)
        else:
            return None

    @property
    def raw_time_series(self) -> pd.DataFrame:
        path = time_series_dir() / f"{self.id}.parquet"
        try:
            time_series = pd.read_parquet(path)
            if "altitude" in time_series.columns:
                time_series.rename(columns={"altitude": "elevation"}, inplace=True)
            return time_series
        except OSError as e:
            logger.error(f"Error while reading {path}.")
            raise

    @property
    def time_series(self) -> pd.DataFrame:
        if self.index_begin or self.index_end:
            return self.raw_time_series.iloc[
                self.index_begin or 0 : self.index_end or -1
            ]
        else:
            return self.raw_time_series


class Tag(DB.Model):
    __tablename__ = "tags"
    __table_args__ = (sa.UniqueConstraint("tag", name="tags_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String, unique=True)

    activities: Mapped[list[Activity]] = relationship(
        secondary=activity_tag_association_table, back_populates="tags"
    )


def get_or_make_tag(tag: str) -> Tag:
    tags = DB.session.scalars(sqlalchemy.select(Tag).where(Tag.tag == tag)).all()
    if tags:
        assert len(tags) == 1, f"There must be only one tag with name '{tag}'."
        return tags[0]
    else:
        tag = Tag(tag=tag)
        DB.session.add(tag)
        return tag


def query_activity_meta(clauses: list = []) -> pd.DataFrame:
    rows = DB.session.execute(
        sqlalchemy.select(
            Activity.id,
            Activity.name,
            Activity.path,
            Activity.distance_km,
            Activity.start,
            Activity.elapsed_time,
            Activity.moving_time,
            Activity.start_latitude,
            Activity.start_longitude,
            Activity.end_latitude,
            Activity.end_longitude,
            Activity.elevation_gain,
            Activity.start_elevation,
            Activity.end_elevation,
            Activity.calories,
            Activity.steps,
            Activity.num_new_tiles_14,
            Activity.num_new_tiles_17,
            Kind.consider_for_achievements,
            Equipment.name.label("equipment"),
            Kind.name.label("kind"),
        )
        .join(Activity.equipment)
        .join(Activity.kind)
        .where(*clauses)
        .order_by(Activity.start)
    ).all()
    df = pd.DataFrame(rows)

    if len(df):
        for old, new in [
            ("elapsed_time", "average_speed_elapsed_kmh"),
            ("moving_time", "average_speed_moving_kmh"),
        ]:
            df[new] = pd.NA
            mask = df[old].dt.total_seconds() > 0
            df.loc[mask, new] = df.loc[mask, "distance_km"] / (
                df.loc[mask, old].dt.total_seconds() / 3_600
            )

        df["date"] = df["start"].dt.date
        df["year"] = df["start"].dt.year
        df["month"] = df["start"].dt.month
        df["day"] = df["start"].dt.day
        df["week"] = df["start"].dt.isocalendar().week
        df["day_of_week"] = df["start"].dt.day_of_week
        df["iso_year"] = df["start"].dt.isocalendar().year
        df["hours"] = df["elapsed_time"].dt.total_seconds() / 3_600
        df["hours_moving"] = df["moving_time"].dt.total_seconds() / 3_600

        df.index = df["id"]

    return df


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


def get_or_make_kind(name: str, config: Config) -> Kind:
    kinds = DB.session.scalars(sqlalchemy.select(Kind).where(Kind.name == name)).all()
    if kinds:
        assert len(kinds) == 1, f"There must be only one kind with name '{name}'."
        return kinds[0]
    else:
        kind = Kind(
            name=name,
            consider_for_achievements=name in config.kinds_without_achievements,
        )
        DB.session.add(kind)
        return kind


class SquarePlannerBookmark(DB.Model):
    __tablename__ = "square_planner_bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)

    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    __table_args__ = (sa.UniqueConstraint("zoom", "x", "y", "size", name="kinds_name"),)


class PlotSpec(DB.Model):
    __tablename__ = "plot_specs"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    mark: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    x: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    y: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    color: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    shape: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    size: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    row: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    opacity: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    column: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    facet: Mapped[str] = mapped_column(sa.String, nullable=False, default="")

    FIELDS = [
        "name",
        "mark",
        "x",
        "y",
        "color",
        "shape",
        "size",
        "row",
        "opacity",
        "column",
        "facet",
    ]

    def __str__(self) -> str:
        return self.name

    def to_json(self) -> str:
        return json.dumps(
            {key: getattr(self, key) for key in self.FIELDS if getattr(self, key)}
        )


class Photo(DB.Model):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str] = mapped_column(sa.String, nullable=False)
    time: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    latitude: Mapped[float] = mapped_column(sa.Float, nullable=False)
    longitude: Mapped[float] = mapped_column(sa.Float, nullable=False)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="activity_id"), nullable=False
    )
    activity: Mapped["Activity"] = relationship(back_populates="photos")

    @property
    def path(self) -> pathlib.Path:
        return pathlib.Path(self.filename)
