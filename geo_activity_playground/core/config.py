import json
import logging

from .datamodel import (
    DB,
    ActivityImportConfig,
    HeartRateConfig,
    MapConfig,
    PrivacyZone,
    StravaConfig,
    UiConfig,
    get_or_make_equipment,
)
from .paths import new_config_file

logger = logging.getLogger(__name__)

_SINGLETONS = (
    HeartRateConfig,
    StravaConfig,
    ActivityImportConfig,
    UiConfig,
    MapConfig,
)


def _singleton(model):
    row = DB.session.get(model, 1)
    if row is None:
        row = model(id=1)
        DB.session.add(row)
        DB.session.commit()
    return row


class ConfigAccessor:
    """Provides the domain-grouped settings singletons stored in the database.

    Each accessor re-fetches its row from the current session, so every request
    and worker process observes the latest committed values.
    """

    def heart_rate(self) -> HeartRateConfig:
        return _singleton(HeartRateConfig)

    def strava(self) -> StravaConfig:
        return _singleton(StravaConfig)

    def activity_import(self) -> ActivityImportConfig:
        return _singleton(ActivityImportConfig)

    def ui(self) -> UiConfig:
        return _singleton(UiConfig)

    def map(self) -> MapConfig:
        return _singleton(MapConfig)

    def save(self) -> None:
        DB.session.commit()

    def ensure_exists(self) -> None:
        for model in _SINGLETONS:
            _singleton(model)


_HEART_RATE_KEYS = ("birth_year", "heart_rate_resting", "heart_rate_maximum")
_STRAVA_KEYS = ("strava_client_id", "strava_client_secret", "strava_client_code")
_ACTIVITY_IMPORT_KEYS = (
    "metadata_extraction_regexes",
    "ignore_suffixes",
    "time_diff_threshold_seconds",
    "reliable_elevation_measurements",
    "kind_renames",
    "segment_max_distance",
    "segment_split_distance",
    "upload_password",
)
_UI_KEYS = (
    "cluster_color_strategy",
    "color_scheme_for_counts",
    "color_scheme_for_kind",
    "color_scheme_for_heatmap",
    "color_strategy_max_cluster_color",
    "color_strategy_max_cluster_other_color",
    "color_strategy_visited_color",
    "color_strategy_cmap_opacity",
    "eighth_marker_min_distance_km",
    "eighth_marker_min_duration_hours",
    "explorer_zoom_levels",
    "show_progress_markers",
    "visible_table_columns",
    "search_map_tiles_per_page",
    "heatmap_cache_min_activities",
    "sharepic_suppressed_fields",
    "kinds_without_achievements",
    "preferred_language",
)
_MAP_KEYS = ("map_tile_url", "map_tile_attribution", "map_style_url")


def _seed(model, data: dict, keys: tuple[str, ...]):
    row = model(id=1)
    for key in keys:
        if key in data:
            setattr(row, key, data[key])
    DB.session.add(row)
    return row


def import_config_json(config_accessor: ConfigAccessor) -> None:
    """One-time migration of a legacy ``config.json`` into the database.

    Only seeds a fresh database; once the settings rows exist the database is
    authoritative and the file is ignored.
    """
    path = new_config_file()
    if not path.exists():
        return
    if DB.session.get(HeartRateConfig, 1) is not None:
        return

    with open(path) as f:
        data = json.load(f)

    _seed(HeartRateConfig, data, _HEART_RATE_KEYS)
    _seed(StravaConfig, data, _STRAVA_KEYS)
    _seed(ActivityImportConfig, data, _ACTIVITY_IMPORT_KEYS)
    _seed(UiConfig, data, _UI_KEYS)
    _seed(MapConfig, data, _MAP_KEYS)

    for name, points in data.get("privacy_zones", {}).items():
        DB.session.add(PrivacyZone(name=name, points=points))

    for name, offset in data.get("equipment_offsets", {}).items():
        equipment = get_or_make_equipment(name)
        if not equipment.offset_km:
            equipment.offset_km = int(offset)
        DB.session.add(equipment)

    DB.session.commit()
    logger.info(
        "Imported settings from 'config.json' into the database. "
        "You can review the settings in the GUI and then delete 'config.json'."
    )
