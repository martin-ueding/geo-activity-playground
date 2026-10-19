import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class GarminAuth(DB.Model):
    """Persistent session tokens and import cursor for Garmin Connect.

    Single-row table. The password is never stored, only the tokens that Garmin
    handed out after the login, which grant access to the account just like a
    password does.
    """

    __tablename__ = "garmin_auth"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_activity_date: Mapped[str | None] = mapped_column(sa.String, nullable=True)


def get_garmin_auth() -> GarminAuth:
    row = DB.session.scalar(sa.select(GarminAuth).limit(1))
    if row is None:
        row = GarminAuth()
        DB.session.add(row)
        DB.session.commit()
    return row
