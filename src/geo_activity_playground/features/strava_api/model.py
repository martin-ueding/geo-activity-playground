import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class StravaConfig(DB.Model):
    """Single-row Strava API credentials."""

    __tablename__ = "config_strava"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    strava_client_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    strava_client_secret: Mapped[str] = mapped_column(
        sa.String, nullable=False, default=""
    )
    strava_client_code: Mapped[str | None] = mapped_column(sa.String, nullable=True)
