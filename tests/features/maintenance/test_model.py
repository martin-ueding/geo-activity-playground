import datetime

from geo_activity_playground.features.maintenance.model import (
    RecurringTask,
    TaskExecution,
)


def make_task(
    interval_days: int | None, interval_km: int | None, done_km: int
) -> RecurringTask:
    task = RecurringTask(
        title="Tire wear", interval_days=interval_days, interval_km=interval_km
    )
    task.executions.append(
        TaskExecution(date=datetime.date(2026, 8, 1), usage_km=done_km)
    )
    return task


def test_zero_interval_counts_as_unset() -> None:
    task = make_task(interval_days=0, interval_km=4000, done_km=12000)
    assert task.next_due_date is None
    assert task.next_due_km == 16000
    assert not task.is_overdue(12000, datetime.date(2026, 8, 1))
    assert task.is_overdue(16000, datetime.date(2026, 8, 1))


def test_overdue_by_date() -> None:
    task = make_task(interval_days=30, interval_km=0, done_km=12000)
    assert task.next_due_date == datetime.date(2026, 8, 31)
    assert task.next_due_km is None
    assert not task.is_overdue(99999, datetime.date(2026, 8, 30))
    assert task.is_overdue(99999, datetime.date(2026, 8, 31))


def test_never_done_is_overdue() -> None:
    task = RecurringTask(title="Tire wear", interval_days=None, interval_km=4000)
    assert task.is_overdue(0, datetime.date(2026, 8, 1))
