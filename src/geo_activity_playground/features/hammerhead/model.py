import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class HammerheadAuth(DB.Model):
    """Persistent OAuth credentials, tokens, and import cursor for the Hammerhead Karoo API.

    Single-row table.
    """

    __tablename__ = "hammerhead_auth"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    client_secret: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    client_code: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    redirect_uri: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    access_token: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime, nullable=True
    )
    last_activity_date: Mapped[str | None] = mapped_column(sa.String, nullable=True)


def get_hammerhead_auth() -> HammerheadAuth:
    row = DB.session.scalar(sa.select(HammerheadAuth).limit(1))
    if row is None:
        row = HammerheadAuth()
        DB.session.add(row)
        DB.session.commit()
    return row
