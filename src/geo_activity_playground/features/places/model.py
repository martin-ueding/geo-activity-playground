import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Activity

PLACE_RADIUS_M = 50.0
MIN_STAY_DURATION = datetime.timedelta(minutes=3)


class Place(DB.Model):
    """A named location created by the user."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    latitude: Mapped[float] = mapped_column(sa.Float, nullable=False)
    longitude: Mapped[float] = mapped_column(sa.Float, nullable=False)

    stays: Mapped[list["Stay"]] = relationship(back_populates="place")


class StayKind(StrEnum):
    START = "start"
    DWELL = "dwell"
    END = "end"


class Stay(DB.Model):
    """A location in an activity where the athlete was stationary.

    The start and end of the activity are stored as stays as well. The place is
    the result of the matching and is recomputed whenever the places change.
    """

    __tablename__ = "stays"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="stay_activity_id"),
        nullable=False,
        index=True,
    )
    activity: Mapped["Activity"] = relationship(back_populates="stays")

    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String, nullable=False)
    latitude: Mapped[float] = mapped_column(sa.Float, nullable=False)
    longitude: Mapped[float] = mapped_column(sa.Float, nullable=False)
    arrival: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
    departure: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", name="stay_place_id"), nullable=True, index=True
    )
    place: Mapped[Place | None] = relationship(back_populates="stays")
