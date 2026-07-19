import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class SquarePlannerBookmark(DB.Model):
    __tablename__ = "square_planner_bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)

    zoom: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    x: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    y: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    __table_args__ = (sa.UniqueConstraint("zoom", "x", "y", "size", name="kinds_name"),)
