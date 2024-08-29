import datetime

import sqlalchemy as sa
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated: Mapped[datetime.timedelta] = mapped_column(sa.DateTime, nullable=False)

    calories: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    consider_for_achievements: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, nullable=False
    )
    distance_km: Mapped[float] = mapped_column(sa.Float, nullable=False)
    elapsed_time: Mapped[datetime.timedelta] = mapped_column(
        sa.Interval, nullable=False
    )
    end_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    end_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    moving_time: Mapped[datetime.timedelta] = mapped_column(sa.Interval, nullable=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    path: Mapped[str] = mapped_column(sa.String, nullable=True)
    start_latitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start_longitude: Mapped[float] = mapped_column(sa.Float, nullable=True)
    start: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
    steps: Mapped[int] = mapped_column(sa.Integer, nullable=True)

    equipment: Mapped["Equipment"] = relationship(back_populates="activities")
    kind: Mapped["Kind"] = relationship(back_populates="activities")
    tile_visits: Mapped[list["TileVisit"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    new_tiles: Mapped["Tile"] = relationship(back_populates="first_visit")


class Equipment(Base):
    __tablename__ = "equipments"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )


class Kind(Base):
    __tablename__ = "kinds"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="kind", cascade="all, delete-orphan"
    )


class Tile(Base):
    __tablename__ = "tiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    zoom: Mapped[int] = mapped_column(sa.Integer, index=True, nullable=False)
    x: Mapped[int] = mapped_column(sa.Integer, index=True, nullable=False)
    y: Mapped[int] = mapped_column(sa.Integer, index=True, nullable=False)

    first_visit: Mapped["Activity"] = relationship(back_populates="new_tiles")
    tile_visits: Mapped[list["TileVisit"]] = relationship(
        back_populates="tile", cascade="all, delete-orphan"
    )


class TileVisit(Base):
    __tablename__ = "tile_visits"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity: Mapped["Activity"] = relationship(back_populates="tile_visits")
    tile: Mapped["Tile"] = relationship(back_populates="tile_visits")
