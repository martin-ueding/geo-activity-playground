import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class TileConfig(DB.Model):
    """Single-row settings for map tile display, such as the hillshade overlay."""

    __tablename__ = "config_tile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    hillshade_opacity: Mapped[float] = mapped_column(
        sa.Float, nullable=False, default=0.5, server_default="0.5"
    )
    hillshade_blend_mode: Mapped[str] = mapped_column(
        sa.String, nullable=False, default="multiply", server_default="multiply"
    )
