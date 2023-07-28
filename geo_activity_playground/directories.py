import functools
import json
import pathlib
import tomllib
from typing import Any

from appdirs import AppDirs


app_dirs = AppDirs("geo-activity-playground", "Martin Ueding")
app_dirs.user_config_dir


@functools.cache
def get_config() -> dict:
    config_path = pathlib.Path(app_dirs.user_config_dir) / "config.toml"
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def get_state(name: str) -> Any:
    state_path = _make_state_path(name)
    print(f"{state_path = }")
    if state_path.exists():
        with open(state_path) as f:
            return json.load(f)


def set_state(name: str, state: Any) -> None:
    state_path = _make_state_path(name)
    state_path.parent.mkdir(exist_ok=True, parents=True)
    with open(_make_state_path(name), "w") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)


def _make_state_path(name: str) -> pathlib.Path:
    return pathlib.Path(app_dirs.user_data_dir) / f"{name}.json"
