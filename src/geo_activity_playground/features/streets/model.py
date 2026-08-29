import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Activity

STREET_REGION_ZOOM = 14
"""Zoom level of the tile grid used to track which regions have already been
fetched from Overpass, so that overlapping activities don't trigger repeated
queries for the same area.

Tiles are fetched along an activity's actual path, not across its bounding
box (a long, mostly-linear activity like a car trip or a point-to-point hike
can have a bounding box that is mostly empty countryside). Zoom 14 -- the
same level this app already uses for "Explorer Tiles" -- keeps each tile
narrow (~1.5 km), so the fetched corridor along a route stays close to the
route itself instead of sweeping up a wide strip of irrelevant land on
either side."""

CHUNK_LENGTH_M = 20.0
"""Target length of a street chunk, both the map-matching graph edge and the
unit street coverage is tracked at."""

SQL_IN_BATCH_SIZE = 400
"""Keep each `IN (...)` query well under SQLite's default 999 bound-parameter
limit; a single Overpass region-tile response, or a long street run, can
involve many thousands of ids in dense areas."""

REGION_PADDING_DEG = 0.002
"""~200 m padding applied around each track point when selecting region
tiles and when querying the local matching graph, so streets just outside
the recorded track are still available."""


class StreetRegion(DB.Model):
    """Marks a coarse region tile as already fetched from Overpass."""

    __tablename__ = "street_regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    fetched_at: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "zoom", "tile_x", "tile_y", name="unique_street_region_tile"
        ),
    )


class StreetWay(DB.Model):
    """One OSM way tagged ``highway=*``."""

    __tablename__ = "street_ways"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, unique=True)
    highway: Mapped[str] = mapped_column(sa.String, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String, nullable=True)


class StreetNode(DB.Model):
    """An OSM node used to build a way's geometry, fetched from Overpass.

    Interpolated points used to subdivide a way into ~20 m chunks are not
    stored here; they only exist implicitly as `StreetChunk` endpoints.
    """

    __tablename__ = "street_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, unique=True)
    lat: Mapped[float] = mapped_column(sa.Float, nullable=False)
    lon: Mapped[float] = mapped_column(sa.Float, nullable=False)


class StreetChunk(DB.Model):
    """A ~20 m piece of a way: both the map-matching graph edge and the unit
    that street coverage is tracked at.

    Built by walking a way's node-to-node polyline and cutting it into
    fixed-length pieces; the last piece of an original node-to-node edge may
    be shorter than `CHUNK_LENGTH_M`.
    """

    __tablename__ = "street_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    way_id: Mapped[int] = mapped_column(
        ForeignKey("street_ways.id", name="street_chunk_way_id"),
        nullable=False,
        index=True,
    )
    way: Mapped["StreetWay"] = relationship(foreign_keys=[way_id])
    seq: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Position of this chunk along the way, starting at 0."""
    lat1: Mapped[float] = mapped_column(sa.Float, nullable=False)
    lon1: Mapped[float] = mapped_column(sa.Float, nullable=False)
    lat2: Mapped[float] = mapped_column(sa.Float, nullable=False)
    lon2: Mapped[float] = mapped_column(sa.Float, nullable=False)
    length_m: Mapped[float] = mapped_column(sa.Float, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("way_id", "seq", name="unique_street_chunk_seq"),
        sa.Index("idx_street_chunks_bbox", "lat1", "lon1", "lat2", "lon2"),
    )


class StreetChunkVisit(DB.Model):
    """Aggregate visit statistics for a street chunk.

    Analogous to `core.datamodel.TileVisit`: the source of truth for "is this
    chunk explored."
    """

    __tablename__ = "street_chunk_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("street_chunks.id", name="street_chunk_visit_chunk_id"),
        nullable=False,
        unique=True,
    )
    chunk: Mapped["StreetChunk"] = relationship(foreign_keys=[chunk_id])

    first_activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="street_chunk_visit_first_activity_id"),
        nullable=False,
        index=True,
    )
    first_activity: Mapped["Activity"] = relationship(foreign_keys=[first_activity_id])
    first_time: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    last_activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="street_chunk_visit_last_activity_id"),
        nullable=False,
        index=True,
    )
    last_activity: Mapped["Activity"] = relationship(foreign_keys=[last_activity_id])
    last_time: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    visit_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class ActivityStreetChunkRun(DB.Model):
    """Which activities pass through which street chunks, run-length encoded.

    A matched GPS track covers contiguous chunks along a way, so this stores
    one row per contiguous stretch (splitting only on a gap or a way change)
    rather than one row per individual chunk. A chunk with a given `seq`
    belongs to a run if `seq_start <= seq <= seq_end`.

    This is the unfiltered record every `StreetChunkVisit` aggregate is
    derived from, analogous to `core.datamodel.ActivityTile`.
    """

    __tablename__ = "activity_street_chunk_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    way_id: Mapped[int] = mapped_column(
        ForeignKey("street_ways.id", name="activity_street_chunk_run_way_id"),
        nullable=False,
        index=True,
    )
    way: Mapped["StreetWay"] = relationship(foreign_keys=[way_id])
    seq_start: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    seq_end: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", name="activity_street_chunk_run_activity_id"),
        nullable=False,
        index=True,
    )
    time_start: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
    time_end: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )

    __table_args__ = (
        sa.Index("idx_activity_street_chunk_run_way", "way_id", "seq_start", "seq_end"),
        sa.Index("idx_activity_street_chunk_run_activity", "activity_id"),
    )
