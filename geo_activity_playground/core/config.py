import functools
import logging
import pathlib


try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


logger = logging.getLogger(__name__)


@functools.cache
def get_config() -> dict:
    config_path = pathlib.Path("config.toml")
    if not config_path.exists():
        logger.warning("Missing a config, some features might be missing.")
        return {}
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Filter out empty config groups.
    config = {key: value for key, value in config.items() if value}

    return config
