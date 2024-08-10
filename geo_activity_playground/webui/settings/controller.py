import json
from typing import Optional

from flask import flash

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.heart_rate import HeartRateZoneComputer


class SettingsController:
    def __init__(self, config_accessor: ConfigAccessor) -> None:
        self._config_accessor = config_accessor

    def render_heart_rate(self) -> dict:
        result = {
            "birth_year": self._config_accessor().birth_year,
            "heart_rate_resting": self._config_accessor().heart_rate_resting,
            "heart_rate_maximum": self._config_accessor().heart_rate_maximum,
        }

        self._heart_rate_computer = HeartRateZoneComputer(
            self._config_accessor().birth_year,
            self._config_accessor().heart_rate_resting,
            self._config_accessor().heart_rate_maximum,
        )
        try:
            result["zone_boundaries"] = self._heart_rate_computer.zone_boundaries()
        except RuntimeError as e:
            pass
        return result

    def save_heart_rate(
        self,
        birth_year: Optional[int],
        heart_rate_resting: Optional[int],
        heart_rate_maximum: Optional[int],
    ) -> None:
        self._config_accessor().birth_year = birth_year
        self._config_accessor().heart_rate_resting = heart_rate_resting
        self._config_accessor().heart_rate_maximum = heart_rate_maximum
        self._config_accessor.save()

    def render_privacy_zones(self) -> dict:
        return {
            "privacy_zones": {
                name: _wrap_coordinates(coordinates)
                for name, coordinates in self._config_accessor().privacy_zones.items()
            }
        }

    def save_privacy_zones(
        self, zone_names: list[str], zone_geojsons: list[str]
    ) -> None:
        assert len(zone_names) == len(zone_geojsons)
        new_zone_config = {}

        for zone_name, zone_geojson_str in zip(zone_names, zone_geojsons):
            if not zone_name or not zone_geojson_str:
                continue

            try:
                zone_geojson = json.loads(zone_geojson_str)
            except json.decoder.JSONDecodeError as e:
                flash(
                    f"Could not parse GeoJSON for {zone_name} due to the following error: {e}"
                )
                continue

            if not zone_geojson["type"] == "FeatureCollection":
                flash(
                    f"Pasted GeoJSON for {zone_name} must be of type 'FeatureCollection'.",
                    category="danger",
                )
                continue

            features = zone_geojson["features"]

            if not len(features) == 1:
                flash(
                    f"Pasted GeoJSON for {zone_name} must contain exactly one feature. You cannot have multiple shapes for one privacy zone",
                    category="danger",
                )
                continue

            feature = features[0]
            geometry = feature["geometry"]

            if not geometry["type"] == "Polygon":
                flash(
                    f"Geometry for {zone_name} is not a polygon. You need to create a polygon (or circle or rectangle).",
                    category="danger",
                )
                continue

            coordinates = geometry["coordinates"]

            if not len(coordinates) == 1:
                flash(
                    f"Polygon for {zone_name} consists of multiple polygons. Please supply a simple one.",
                    category="danger",
                )
                continue

            points = coordinates[0]

            new_zone_config[zone_name] = points

        self._config_accessor().privacy_zones = new_zone_config
        self._config_accessor.save()


def _wrap_coordinates(coordinates: list[list[float]]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"coordinates": [coordinates], "type": "Polygon"},
            }
        ],
    }
