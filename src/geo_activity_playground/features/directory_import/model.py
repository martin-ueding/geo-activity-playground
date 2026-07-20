import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ...core.datamodel import DB


class BrokenActivityFile(DB.Model):
    """An activity file that failed to import, so it is not retried on every scan.

    Keyed by path with the file hash at the time of the failed attempt: if the
    file changes (edited, replaced), the hash no longer matches and the next
    scan retries it.
    """

    __tablename__ = "broken_activity_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(sa.String, nullable=False, unique=True)
    file_hash: Mapped[str] = mapped_column(sa.String, nullable=False)
    reason: Mapped[str] = mapped_column(sa.String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_attempt: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)
