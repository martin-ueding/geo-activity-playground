import json

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class PlotSpec(DB.Model):
    __tablename__ = "plot_specs"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(sa.String, nullable=False)

    mark: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    x: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    y: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    color: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    shape: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    size: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    row: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    opacity: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    column: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    facet: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    group_by: Mapped[str] = mapped_column(sa.String, nullable=True, default="")

    FIELDS = [
        "name",
        "mark",
        "x",
        "y",
        "color",
        "shape",
        "size",
        "row",
        "opacity",
        "column",
        "facet",
        "group_by",
    ]

    def __str__(self) -> str:
        return self.name

    def to_json(self) -> str:
        return json.dumps(
            {key: getattr(self, key) for key in self.FIELDS if getattr(self, key)}
        )
