import contextlib
import json
import pathlib


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
