"""Periodic SQLite housekeeping.

Deleting cached tiles leaves the database file full of free pages, which slows
down every subsequent scan. `VACUUM` rebuilds the file compactly and `ANALYZE`
refreshes the statistics that the query planner uses on the large tile tables.
"""

import datetime
import logging
from collections.abc import Callable, Sequence

from .datamodel import DB, DatabaseMaintenanceState

logger = logging.getLogger(__name__)

MAINTENANCE_INTERVAL = datetime.timedelta(days=30)
VACUUM_FREELIST_FRACTION = 0.1


def run_database_maintenance_if_due(
    tasks: Sequence[Callable[[], object]] = (),
    interval: datetime.timedelta = MAINTENANCE_INTERVAL,
) -> bool:
    """Vacuum and analyze the database if it hasn't been done in `interval`.

    The callables in `tasks` run first, so that space they free is reclaimed by
    the same vacuum.
    """
    state = DB.session.get(DatabaseMaintenanceState, 1)
    if state is None:
        state = DatabaseMaintenanceState(id=1)
        DB.session.add(state)
        DB.session.commit()

    now = datetime.datetime.now()
    if state.last_run is not None and now - state.last_run < interval:
        return False

    for task in tasks:
        task()

    DB.session.commit()
    with DB.engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        page_count = connection.exec_driver_sql("pragma page_count").scalar() or 0
        freelist_count = (
            connection.exec_driver_sql("pragma freelist_count").scalar() or 0
        )
        if page_count and freelist_count / page_count > VACUUM_FREELIST_FRACTION:
            logger.info(
                "Vacuuming the database to reclaim %d of %d pages, this may take a few minutes.",
                freelist_count,
                page_count,
            )
            connection.exec_driver_sql("vacuum")
        logger.info("Analyzing the database to refresh query planner statistics.")
        connection.exec_driver_sql("analyze")

    state.last_run = now
    DB.session.commit()
    return True
