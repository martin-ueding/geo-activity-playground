import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class HeatmapTileCache(DB.Model):
    __tablename__ = "heatmap_tile_cache"
    __table_args__ = (
        sa.Index(
            "idx_heatmap_tile_cache_lookup",
            "zoom",
            "tile_x",
            "tile_y",
            "search_query_id",
        ),
        sa.UniqueConstraint(
            "zoom",
            "tile_x",
            "tile_y",
            "search_query_id",
            name="uq_heatmap_tile_cache_tile_query",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    search_query_id: Mapped[int | None] = mapped_column(
        ForeignKey("stored_search_queries.id", name="heatmap_cache_search_query_id"),
        nullable=True,
        index=True,
    )
    counts: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    included_activity_ids: Mapped[list[int]] = mapped_column(sa.JSON, nullable=False)
    num_activities: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_used: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
