import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Activity

QUANTILES = ["p25", "p50", "p75", "p95", "p100", "mean"]


class RouteDistance(DB.Model):
    """Distances in meters from the points of an activity to a reference track.

    The quantiles are `None` when the tracks are too far apart to compare them
    in detail. The row then only records that the pair has been checked.
    """

    __tablename__ = "route_distances"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="route_distance_activity_id"),
        primary_key=True,
    )
    activity: Mapped["Activity"] = relationship(
        foreign_keys=[activity_id], back_populates="route_distances"
    )

    reference_activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="route_distance_reference_activity_id"),
        primary_key=True,
        index=True,
    )
    reference_activity: Mapped["Activity"] = relationship(
        foreign_keys=[reference_activity_id],
        back_populates="reference_route_distances",
    )

    p25: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    p50: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    p75: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    p95: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    p100: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    mean: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    checked_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.datetime.now
    )
