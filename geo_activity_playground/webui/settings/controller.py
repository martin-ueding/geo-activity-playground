import json
import re
import urllib.parse
from typing import Any
from typing import Optional

from flask import flash
from flask import url_for

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.heart_rate import HeartRateZoneComputer


SHAREPIC_FIELDS = {
    "calories": "Calories",
    "distance_km": "Distance",
    "elapsed_time": "Elapsed time",
    "equipment": "Equipment",
    "kind": "Kind",
    "name": "Name",
    "start": "Date",
    "Steps": "Steps",
}


class SettingsController:
    def __init__(self, config_accessor: ConfigAccessor) -> None:
        self._config_accessor = config_accessor

    def render_admin_password(self) -> dict:
        return {
            "password": self._config_accessor().upload_password,
        }

    def save_admin_password(self, password: str) -> None:
        self._config_accessor().upload_password = password
        self._config_accessor.save()
        flash("Updated admin password.", category="success")

    def render_equipment_offsets(self) -> dict:
        return {
            "equipment_offsets": self._config_accessor().equipment_offsets,
        }

    def save_equipment_offsets(
        self,
        equipments: list[str],
        offsets: list[str],
    ) -> None:
        assert len(equipments) == len(offsets)
        new_equipment_offsets = {}
        for equipment, offset_str in zip(equipments, offsets):
            if not equipment or not offset_str:
                continue

            try:
                offset = float(offset_str)
            except ValueError as e:
                flash(
                    f"Cannot parse number {offset_str} for {equipment}: {e}",
                    category="danger",
                )
                continue

            if not offset:
                continue

            new_equipment_offsets[equipment] = offset
        self._config_accessor().equipment_offsets = new_equipment_offsets
        self._config_accessor.save()
        flash("Updated equipment offsets.", category="success")

    def render_heart_rate(self) -> dict:
        result: dict[str, Any] = {
            "birth_year": self._config_accessor().birth_year,
            "heart_rate_resting": self._config_accessor().heart_rate_resting,
            "heart_rate_maximum": self._config_accessor().heart_rate_maximum,
        }

        self._heart_rate_computer = HeartRateZoneComputer(self._config_accessor())
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
        self._config_accessor().heart_rate_resting = heart_rate_resting or 0
        self._config_accessor().heart_rate_maximum = heart_rate_maximum
        self._config_accessor.save()
        flash("Updated heart rate data.", category="success")

    def render_kinds_without_achievements(self) -> dict:
        return {
            "kinds_without_achievements": self._config_accessor().kinds_without_achievements,
        }

    def save_kinds_without_achievements(
        self,
        kinds: list[str],
    ) -> None:
        new_kinds = [kind.strip() for kind in kinds if kind.strip()]
        new_kinds.sort()

        self._config_accessor().kinds_without_achievements = new_kinds
        self._config_accessor.save()
        flash("Updated kinds without achievements.", category="success")

    def render_metadata_extraction(self) -> dict:
        return {
            "metadata_extraction_regexes": self._config_accessor().metadata_extraction_regexes,
        }

    def save_metadata_extraction(
        self,
        metadata_extraction_regexes: list[str],
    ) -> None:
        new_metadata_extraction_regexes = []
        for regex in metadata_extraction_regexes:
            try:
                re.compile(regex)
            except re.error as e:
                flash(
                    f"Cannot parse regex {regex} due to error: {e}", category="danger"
                )
            else:
                new_metadata_extraction_regexes.append(regex)

        self._config_accessor().metadata_extraction_regexes = (
            new_metadata_extraction_regexes
        )
        self._config_accessor.save()
        flash("Updated metadata extraction settings.", category="success")

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
        flash("Updated privacy zones.", category="success")

    def render_sharepic(self) -> dict:

        return {
            "names": [
                (
                    name,
                    label,
                    name not in self._config_accessor().sharepic_suppressed_fields,
                )
                for name, label in SHAREPIC_FIELDS.items()
            ]
        }

    def save_sharepic(self, names: list[str]) -> None:
        self._config_accessor().sharepic_suppressed_fields = list(
            set(SHAREPIC_FIELDS) - set(names)
        )
        self._config_accessor.save()
        flash("Updated sharepic preferences.", category="success")
        pass

    def render_strava(self) -> dict:
        return {
            "strava_client_id": self._config_accessor().strava_client_id,
            "strava_client_secret": self._config_accessor().strava_client_secret,
            "strava_client_code": self._config_accessor().strava_client_code,
        }

    def save_strava(self, client_id: str, client_secret: str) -> str:
        self._strava_client_id = client_id
        self._strava_client_secret = client_secret

        payload = {
            "client_id": client_id,
            "redirect_uri": url_for(".strava_callback", _external=True),
            "response_type": "code",
            "scope": "activity:read_all",
        }

        arg_string = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in payload.items()
        )
        return f"https://www.strava.com/oauth/authorize?{arg_string}"

    def save_strava_code(self, code: str) -> None:
        self._config_accessor().strava_client_id = int(self._strava_client_id)
        self._config_accessor().strava_client_secret = self._strava_client_secret
        self._config_accessor().strava_client_code = code
        self._config_accessor.save()
        flash("Connected to Strava API", category="success")


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
