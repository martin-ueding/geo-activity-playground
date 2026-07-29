import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Activity


class ExplorerTileBookmark(DB.Model):
    __tablename__ = "explorer_tile_bookmarks"
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.tile_x}, {self.tile_y}) @ {self.zoom}"


class ClusterHistoryEvent(DB.Model):
    __tablename__ = "cluster_history_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    event_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="cluster_history_event_activity_id"),
        nullable=False,
        index=True,
    )
    activity: Mapped["Activity"] = relationship(foreign_keys=[activity_id])
    time: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    __table_args__ = (
        sa.Index("idx_cluster_history_events_zoom_index", "zoom", "event_index"),
        sa.Index("idx_cluster_history_events_zoom_time", "zoom", "time"),
        sa.UniqueConstraint("zoom", "event_index", name="uq_cluster_history_events"),
    )


class ClusterHistoryCheckpoint(DB.Model):
    __tablename__ = "cluster_history_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    event_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    time: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True)
    max_cluster_size: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    payload_json: Mapped[str] = mapped_column(sa.Text, nullable=False, default="{}")

    __table_args__ = (
        sa.Index("idx_cluster_history_checkpoints_zoom_index", "zoom", "event_index"),
        sa.UniqueConstraint(
            "zoom", "event_index", name="uq_cluster_history_checkpoints"
        ),
    )


class ExplorerSquare(DB.Model):
    """Current biggest explorer square per zoom level."""

    __tablename__ = "explorer_square"

    zoom: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    square_x: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    square_y: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    max_square_size: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class SquareHistory(DB.Model):
    """Time series of the biggest explorer square, for the evolution plot."""

    __tablename__ = "square_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    time: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True)
    max_square_size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    square_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    square_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class ClusterSizeHistory(DB.Model):
    """Time series of the biggest cluster size, for the evolution plot."""

    __tablename__ = "cluster_size_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    time: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime, nullable=True)
    max_cluster_size: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class ClusterMembership(DB.Model):
    """Materialized current cluster membership per tile.

    Holds, for every cluster tile at a zoom level, the representative tile of
    its cluster (``cluster_x``/``cluster_y``). This is the source of truth for
    the live explorer cluster coloring and counters, queried by viewport so no
    per-process in-memory state is needed.
    """

    __tablename__ = "cluster_membership"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    cluster_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    cluster_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    __table_args__ = (
        sa.Index("idx_cluster_membership_zoom_tile", "zoom", "tile_x", "tile_y"),
        sa.Index(
            "idx_cluster_membership_zoom_cluster", "zoom", "cluster_x", "cluster_y"
        ),
        sa.UniqueConstraint(
            "zoom", "tile_x", "tile_y", name="uq_cluster_membership_per_zoom"
        ),
    )
