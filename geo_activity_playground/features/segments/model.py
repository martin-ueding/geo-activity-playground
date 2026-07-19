import datetime
import json

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Activity


class Segment(DB.Model):
    """A user-defined segment (polyline) for tracking repeated efforts."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    # Coordinates as a `list[tuple[float, float]]` with lat-lon order. That is opposite to GeoJSON.
    coordinates_json: Mapped[str] = mapped_column(sa.Text, nullable=False, default="[]")

    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    matches: Mapped[list["SegmentMatch"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )

    checks: Mapped[list["SegmentCheck"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )

    @property
    def coordinates(self) -> list[list[float]]:
        """Get coordinates as list of [lat, lon] pairs."""
        return json.loads(self.coordinates_json)

    @coordinates.setter
    def coordinates(self, value: list[list[float]]) -> None:
        """Set coordinates from list of [lat, lon] pairs."""
        self.coordinates_json = json.dumps(value)

    @property
    def length_km(self) -> float:
        """Calculate approximate length of segment in kilometers."""
        from ...core.coordinates import get_distance

        coords = self.coordinates
        total = 0.0
        for i in range(len(coords) - 1):
            lat1, lon1 = coords[i]
            lat2, lon2 = coords[i + 1]
            total += get_distance(lat1, lon1, lat2, lon2)
        return total / 1000  # Convert meters to km

    def __str__(self) -> str:
        return f"{self.name} ({self.length_km:.2f} km)"


class SegmentMatch(DB.Model):
    """Records when an activity passes through a segment.

    Stores the entry and exit points/times for computing segment duration
    and comparing efforts.
    """

    __tablename__ = "segment_matches"

    id: Mapped[int] = mapped_column(primary_key=True)

    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", name="segment_match_segment_id"),
        nullable=False,
        index=True,
    )
    segment: Mapped["Segment"] = relationship(back_populates="matches")

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="segment_match_activity_id"),
        nullable=False,
        index=True,
    )
    activity: Mapped["Activity"] = relationship(back_populates="segment_matches")

    # Entry point in the activity time series
    entry_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    entry_time: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Exit point in the activity time series
    exit_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    exit_time: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    # Computed duration for easy querying/sorting
    duration: Mapped[datetime.timedelta | None] = mapped_column(
        sa.Interval, nullable=True
    )

    # Distance covered in this segment effort (may differ slightly from segment length)
    distance_km: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    # Average power across this segment effort, when available on the activity.
    power_avg: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    def __repr__(self) -> str:
        duration_str = str(self.duration).split(".")[0] if self.duration else "unknown"
        return f"SegmentMatch(segment={self.segment.name}, activity={self.activity_id}, duration={duration_str})"


class SegmentCheck(DB.Model):
    """Records when an activity passes through a segment.

    Stores the entry and exit points/times for computing segment duration
    and comparing efforts.
    """

    __tablename__ = "segment_checks"

    id: Mapped[int] = mapped_column(primary_key=True)

    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segments.id", name="segment_check_segment_id"),
        nullable=False,
        index=True,
    )
    segment: Mapped["Segment"] = relationship(back_populates="checks")

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="segment_check_activity_id"),
        nullable=False,
        index=True,
    )
    activity: Mapped["Activity"] = relationship(back_populates="segment_checks")

    __table_args__ = (
        sa.UniqueConstraint(
            "segment_id", "activity_id", name="unique_segment_activity_check"
        ),
    )
