import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .datamodel import DB


class ImportExclusion(DB.Model):
    """An upstream activity that must not be (re-)imported.

    Either the file could not be parsed, or the user deleted the activity. The
    key is the upstream identity: the file content hash for directory imports,
    the remote activity id for API sources. A changed file therefore gets a new
    hash and is retried automatically.
    """

    __tablename__ = "import_exclusions"
    __table_args__ = (sa.UniqueConstraint("source", "upstream_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(sa.String, nullable=False)
    upstream_id: Mapped[str] = mapped_column(sa.String, nullable=False)
    path: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    reason: Mapped[str] = mapped_column(sa.String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_attempt: Mapped[datetime.datetime] = mapped_column(sa.DateTime, nullable=False)


def record_exclusion(
    source: str,
    upstream_id: str,
    reason: str,
    path: str | None = None,
    error_message: str | None = None,
) -> None:
    exclusion = DB.session.scalar(
        sa.select(ImportExclusion).filter(
            ImportExclusion.source == source,
            ImportExclusion.upstream_id == upstream_id,
        )
    )

    if path is not None:
        for stale in DB.session.scalars(
            sa.select(ImportExclusion).filter(
                ImportExclusion.source == source,
                ImportExclusion.path == path,
                ImportExclusion.upstream_id != upstream_id,
            )
        ).all():
            DB.session.delete(stale)

    if exclusion is None:
        exclusion = ImportExclusion(source=source, upstream_id=upstream_id)
        DB.session.add(exclusion)
    exclusion.path = path
    exclusion.reason = reason
    exclusion.error_message = error_message
    exclusion.last_attempt = datetime.datetime.now(datetime.UTC)
    DB.session.commit()


def is_excluded(source: str, upstream_id: str) -> bool:
    return (
        DB.session.scalar(
            sa.select(ImportExclusion).filter(
                ImportExclusion.source == source,
                ImportExclusion.upstream_id == upstream_id,
            )
        )
        is not None
    )


def clear_exclusion(source: str, upstream_id: str) -> None:
    DB.session.execute(
        sa.delete(ImportExclusion).where(
            ImportExclusion.source == source,
            ImportExclusion.upstream_id == upstream_id,
        )
    )
