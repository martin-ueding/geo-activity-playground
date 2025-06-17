import dataclasses
import functools
import json
import logging
import pathlib
from typing import Optional

from .paths import new_config_file
from .paths import strava_dynamic_config_path


try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Config:
    birth_year: Optional[int] = None
    cluster_color_strategy: str = "colorful_cluster"
    color_scheme_for_counts: str = "teals"
    color_scheme_for_kind: str = "category10"
    color_scheme_for_heatmap: str = "hot"
    equipment_offsets: dict[str, float] = dataclasses.field(default_factory=dict)
    explorer_zoom_levels: list[int] = dataclasses.field(
        default_factory=lambda: [14, 17]
    )
    heart_rate_resting: int = 0
    heart_rate_maximum: Optional[int] = None
    ignore_suffixes: list[str] = dataclasses.field(default_factory=list)
    kind_renames: dict[str, str] = dataclasses.field(default_factory=dict)
    kinds_without_achievements: list[str] = dataclasses.field(default_factory=list)
    metadata_extraction_regexes: list[str] = dataclasses.field(default_factory=list)
    num_processes: Optional[int] = 1
    privacy_zones: dict[str, list[list[float]]] = dataclasses.field(
        default_factory=dict
    )
    reliable_elevation_measurements: bool = True
    sharepic_suppressed_fields: list[str] = dataclasses.field(default_factory=list)
    strava_client_id: int = 131693
    strava_client_secret: str = "0ccc0100a2c218512a7ef0cea3b0e322fb4b4365"
    strava_client_code: Optional[str] = None
    time_diff_threshold_seconds: Optional[int] = 30
    upload_password: Optional[str] = None
    map_tile_url: str = "https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    map_tile_attribution: str = (
        '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | <a href="https://www.openstreetmap.org/fixthemap">Correct Map</a>'
    )
    search_queries_favorites: list[dict] = dataclasses.field(default_factory=list)
    search_queries_last: list[dict] = dataclasses.field(default_factory=list)
    search_queries_num_keep: int = 10


class ConfigAccessor:
    def __init__(self) -> None:
        if new_config_file().exists():
            with open(new_config_file()) as f:
                self._config = Config(**json.load(f))
        else:
            self._config = Config()

    def __call__(self) -> Config:
        return self._config

    def save(self) -> None:
        with open(new_config_file(), "w") as f:
            json.dump(
                dataclasses.asdict(self._config),
                f,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )


@functools.cache
def get_config() -> dict:
    config_path = pathlib.Path("config.toml")
    if not config_path.exists():
        logger.warning("Missing a config, some features might be missing.")
        return {}
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    return config


def import_old_config(config_accessor: ConfigAccessor) -> None:
    old_config_path = pathlib.Path("config.toml")
    if not old_config_path.exists():
        return

    if new_config_file().exists():
        logger.warning(
            "You have an old 'config.toml' which is now superseded by the 'config.json'. You can check the contents of the new 'config.json' and then delete the old 'config.toml'."
        )
        return

    old_config = get_config()
    config = config_accessor()

    if "metadata_extraction_regexes" in old_config:
        config.metadata_extraction_regexes = old_config["metadata_extraction_regexes"]

    if "heart" in old_config:
        if "birthyear" in old_config["heart"]:
            config.birth_year = old_config["heart"]["birthyear"]
        if "resting" in old_config["heart"]:
            config.heart_rate_resting = old_config["heart"]["resting"]
        if "maximum" in old_config["heart"]:
            config.heart_rate_maximum = old_config["heart"]["maximum"]

    if "strava" in old_config:
        if "client_id" in old_config["strava"]:
            config.strava_client_id = old_config["strava"]["client_id"]
        if "client_secret" in old_config["strava"]:
            config.strava_client_secret = old_config["strava"]["client_secret"]
        if "code" in old_config["strava"]:
            config.strava_client_code = old_config["strava"]["code"]

    if "offsets" in old_config:
        config.equipment_offsets = old_config["offsets"]

    if "upload" in old_config:
        if "password" in old_config["upload"]:
            config.upload_password = old_config["upload"]["password"]

    if "privacy_zones" in old_config:
        config.privacy_zones = old_config["privacy_zones"]

    config_accessor.save()


def import_old_strava_config(config_accessor: ConfigAccessor) -> None:
    if not strava_dynamic_config_path().exists():
        return

    with open(strava_dynamic_config_path()) as f:
        strava_dynamic_config = json.load(f)

    config = config_accessor()
    config.strava_client_id = strava_dynamic_config["client_id"]
    config.strava_client_secret = strava_dynamic_config["client_secret"]
    config.strava_client_code = strava_dynamic_config["code"]

    config_accessor.save()
    strava_dynamic_config_path().unlink()
