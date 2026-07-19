import datetime
import pathlib

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.datamodel import DB, Activity


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
