import contextlib
import json
import pathlib
import pickle
from collections.abc import Iterable
from typing import Any
from typing import Generic
from typing import Sequence
from typing import TypeVar

from .paths import atomic_open
from .paths import cache_dir


T = TypeVar("T")


@contextlib.contextmanager
def stored_object(path: pathlib.Path, default):
    if path.exists():
        with open(path, "rb") as f:
            payload = pickle.load(f)
    else:
        payload = default

    yield payload

    with atomic_open(path, "wb") as f:
        pickle.dump(payload, f)


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
        json.dump(list(s), f, indent=2, sort_keys=True)


class WorkTracker:
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

        if self._path.exists():
            with open(self._path, "rb") as f:
                self._done = pickle.load(f)
        else:
            self._done = set()

    def filter(self, ids: Iterable) -> list:
        return [elem for elem in ids if elem not in self._done]

    def mark_done(self, id: int) -> None:
        self._done.add(id)

    def discard(self, id) -> None:
        self._done.discard(id)

    def reset(self) -> None:
        self._done = set()

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


class TransformVersion:
    def __init__(self, path: pathlib.Path, code_version: int) -> None:
        self._path = path
        self._code_version = code_version

        with open(path) as f:
            self._actual_version = json.load(f)

        assert (
            self._actual_version <= self._code_version
        ), "You attempt to use a more modern playground with an older code version, that is not supported."

    def outdated(self) -> bool:
        return self._actual_version < self._code_version

    def write(self) -> None:
        with open(self._path, "w") as f:
            json.dump(self._code_version, f)


def get_state(path: pathlib.Path, default: Any) -> Any:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    else:
        return default


def set_state(path: pathlib.Path, state: Any) -> None:
    path.parent.mkdir(exist_ok=True, parents=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
