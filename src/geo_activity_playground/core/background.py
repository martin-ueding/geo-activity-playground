"""Long-running work that happens while the web server is serving requests.

Gunicorn runs several worker processes, each of which starts the runner. A file
lock makes sure that only one of them executes the tasks. When that worker
exits, the kernel releases the lock and a runner in another worker takes over.
"""

import contextlib
import logging
import threading
import time
from collections.abc import Iterator, Sequence
from typing import Protocol

from flask import Flask

from .paths import cache_dir

try:
    import fcntl
except ImportError:
    # Windows only supports single-process servers, so there is nothing to exclude.
    fcntl = None

logger = logging.getLogger(__name__)

IDLE_INTERVAL_S = 300


class BackgroundTask(Protocol):
    def run_step(self) -> bool:
        """Do a bounded chunk of work and return whether more work is pending."""
        ...


def start_background_tasks(app: Flask, tasks: Sequence[BackgroundTask]) -> None:
    threading.Thread(
        target=_run_forever, args=(app, tasks), name="background-tasks", daemon=True
    ).start()


def run_step_of_each(app: Flask, tasks: Sequence[BackgroundTask]) -> bool:
    busy = False
    for task in tasks:
        with app.app_context():
            try:
                busy |= task.run_step()
            except Exception:
                logger.exception(f"Background task {type(task).__name__} failed.")
    return busy


def _run_forever(app: Flask, tasks: Sequence[BackgroundTask]) -> None:
    with _exclusive_lock():
        logger.info("Running background tasks in this process.")
        while True:
            if not run_step_of_each(app, tasks):
                time.sleep(IDLE_INTERVAL_S)


@contextlib.contextmanager
def _exclusive_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    with open(cache_dir() / "background-tasks.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
