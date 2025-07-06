import datetime
import zoneinfo

import pytest
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Session


class MyTestBase(DeclarativeBase):
    pass


class MyTestEvent(MyTestBase):
    __tablename__ = "events"

    # Housekeeping data:
    id: Mapped[int] = mapped_column(primary_key=True)
    time: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


@pytest.mark.xfail(reason="SQLite cannot store time zones.")
def test_timezone_sqlalchemy() -> None:
    engine = sa.create_engine("sqlite://", echo=False)
    MyTestBase.metadata.create_all(engine)

    dt_berlin = datetime.datetime(
        2025, 7, 1, 14, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Berlin")
    )

    with Session(engine) as session:
        event = MyTestEvent(time=dt_berlin)
        session.add(event)
        session.commit()
        assert event.time == dt_berlin
