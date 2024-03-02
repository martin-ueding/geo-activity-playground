import contextlib
import json
import pathlib
import pickle
from collections.abc import Iterable
from typing import Any
from typing import Generic
from typing import Sequence
from typing import TypeVar

from geo_activity_playground.core.paths import cache_dir


T = TypeVar("T")


@contextlib.contextmanager
def stored_object(path: pathlib.Path, default):
    if path.exists():
        with open(path, "rb") as f:
            payload = pickle.load(f)
    else:
        payload = default

    yield payload

    temp_location = path.with_suffix(".tmp")
    with open(temp_location, "wb") as f:
        pickle.dump(payload, f)
    path.unlink(missing_ok=True)
    temp_location.rename(path)


def work_tracker_path(name: str) -> pathlib.Path:
    return cache_dir() / f"work-tracker-{name}.pickle"


@contextlib.contextmanager
def work_tracker(path: pathlib.Path):
    if path.exists():
        with open(path) as f:
            s = set(json.load(f))
    else:
        s = set()

    yield s

    with open(path, "w") as f:
        json.dump(list(s), f)


class WorkTracker:
    def __init__(self, name: str) -> None:
        self._path = work_tracker_path(name)

        if self._path.exists():
            with open(self._path, "rb") as f:
                self._done = pickle.load(f)
        else:
            self._done = set()

    def filter(self, ids: Iterable[int]) -> set[int]:
        return set(ids) - self._done

    def mark_done(self, id: int) -> None:
        self._done.add(id)

    def close(self) -> None:
        with open(self._path, "wb") as f:
            pickle.dump(self._done, f)


def try_load_pickle(path: pathlib.Path) -> Any:
    if path.exists():
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except ModuleNotFoundError:
            pass
