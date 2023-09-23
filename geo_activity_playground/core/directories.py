import functools
import json
import os
import pathlib
import tomllib
from typing import Any


@functools.cache
def get_config() -> dict:
    config_path = pathlib.Path(os.getcwd()) / "config.toml"
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def get_state(path: pathlib.Path) -> Any:
    if path.exists():
        with open(path) as f:
            return json.load(f)


def set_state(path: pathlib.Path, state: Any) -> None:
    path.parent.mkdir(exist_ok=True, parents=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)
