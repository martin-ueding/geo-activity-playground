import json
import re
import shutil
import urllib.parse
from typing import Any
from typing import Optional

from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for

from ...core.config import ConfigAccessor
from ...core.heart_rate import HeartRateZoneComputer
from ...core.paths import _activity_enriched_dir
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes

VEGA_COLOR_SCHEMES_CONTINUOUS = [
    "lightgreyred",
    "lightgreyteal",
    "lightmulti",
    "lightorange",
    "lighttealblue",
    "blues",
    "tealblues",
    "teals",
    "greens",
    "browns",
    "oranges",
    "reds",
    "purples",
    "warmgreys",
    "greys",
]

MATPLOTLIB_COLOR_SCHEMES_CONTINUOUS = [
    "afmhot",
    "bone",
    "cividis",
    "copper",
    "gist_gray",
    "gist_heat",
    "gnuplot2",
    "gray",
    "Greys_r",
    "hot",
    "inferno",
    "magma",
    "pink",
    "plasma",
    "viridis",
]


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


def int_or_none(s: str) -> Optional[int]:
    if s:
        try:
            return int(s)
        except ValueError as e:
            flash(f"Cannot parse integer from {s}: {e}", category="danger")
    return None


def make_settings_blueprint(
    config_accessor: ConfigAccessor, authenticator: Authenticator, flasher: Flasher
) -> Blueprint:
    strava_login_helper = StravaLoginHelper(config_accessor)
    blueprint = Blueprint("settings", __name__, template_folder="templates")

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        return render_template("settings/index.html.j2")

    @blueprint.route("/admin-password")
    @needs_authentication(authenticator)
    def admin_password() -> Response:
        if request.method == "POST":
            config_accessor().upload_password = request.form["password"]
            config_accessor.save()
            flasher.flash_message("Updated admin password.", FlashTypes.SUCCESS)
        return render_template(
            "settings/admin-password.html.j2",
            password=config_accessor().upload_password,
        )

    @blueprint.route("/color-schemes", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def color_schemes():
        if request.method == "POST":
            config_accessor().color_scheme_for_counts = request.form[
                "color_scheme_for_counts"
            ]
            config_accessor().color_scheme_for_kind = request.form[
                "color_scheme_for_kind"
            ]
            config_accessor().color_scheme_for_heatmap = request.form[
                "color_scheme_for_heatmap"
            ]
            config_accessor.save()
            flash("Updated color schemes.", category="success")

        return render_template(
            "settings/color-schemes.html.j2",
            color_scheme_for_counts=config_accessor().color_scheme_for_counts,
            color_scheme_for_counts_avail=VEGA_COLOR_SCHEMES_CONTINUOUS,
            color_scheme_for_kind=config_accessor().color_scheme_for_kind,
            color_scheme_for_kind_avail=[
                "accent",
                "category10",
                "category20",
                "category20b",
                "category20c",
                "dark2",
                "paired",
                "pastel1",
                "pastel2",
                "set1",
                "set2",
                "set3",
                "tableau10",
                "tableau20",
            ],
            color_scheme_for_heatmap=config_accessor().color_scheme_for_heatmap,
            color_scheme_for_heatmap_avail=MATPLOTLIB_COLOR_SCHEMES_CONTINUOUS,
        )

    @blueprint.route("/equipment-offsets", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def equipment_offsets():
        if request.method == "POST":
            equipments = request.form.getlist("equipment")
            offsets = request.form.getlist("offset")
            strava_login_helper.save_equipment_offsets(equipments, offsets)
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
            config_accessor().equipment_offsets = new_equipment_offsets
            config_accessor.save()
        flash("Updated equipment offsets.", category="success")
        context = {
            "equipment_offsets": config_accessor().equipment_offsets,
        }
        return render_template("settings/equipment-offsets.html.j2", **context)

    @blueprint.route("/heart-rate", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def heart_rate():
        if request.method == "POST":
            birth_year = int_or_none(request.form["birth_year"])
            heart_rate_resting = int_or_none(request.form["heart_rate_resting"])
            if heart_rate_resting is None:
                heart_rate_resting = 0
            heart_rate_maximum = int_or_none(request.form["heart_rate_maximum"])
            config_accessor().birth_year = birth_year
            config_accessor().heart_rate_resting = heart_rate_resting or 0
            config_accessor().heart_rate_maximum = heart_rate_maximum
            config_accessor.save()
            flash("Updated heart rate data.", category="success")

        context: dict[str, Any] = {
            "birth_year": config_accessor().birth_year,
            "heart_rate_resting": config_accessor().heart_rate_resting,
            "heart_rate_maximum": config_accessor().heart_rate_maximum,
        }

        heart_rate_computer = HeartRateZoneComputer(config_accessor())
        try:
            context["zone_boundaries"] = heart_rate_computer.zone_boundaries()
        except RuntimeError as e:
            pass
        return render_template("settings/heart-rate.html.j2", **context)

    @blueprint.route("/kind-renames", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def kind_renames():
        if request.method == "POST":
            rules_str = request.form["rules_str"]
            rules = {}
            try:
                for line in rules_str.strip().split("\n"):
                    first, second = line.split(" => ")
                    rules[first.strip()] = second.strip()
                config_accessor().kind_renames = rules
                config_accessor.save()
                flash(f"Kind renames updated.", category="success")
                shutil.rmtree(_activity_enriched_dir)
                return redirect(url_for("upload.reload"))
            except ValueError as e:
                flash(f"Cannot parse this. Please try again.", category="danger")
        else:
            rules_str = "\n".join(
                f"{key} =&gt; {value}"
                for key, value in config_accessor().kind_renames.items()
            )
        return render_template(
            "settings/kind-renames.html.j2",
            rules_str=rules_str,
        )

    @blueprint.route("/kinds-without-achievements", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def kinds_without_achievements():
        if request.method == "POST":
            kinds = request.form.getlist("kind")
            new_kinds = [kind.strip() for kind in kinds if kind.strip()]
            new_kinds.sort()

            config_accessor().kinds_without_achievements = new_kinds
            config_accessor.save()
            flash("Updated kinds without achievements.", category="success")
            strava_login_helper.save_kinds_without_achievements(kinds)
        context = {
            "kinds_without_achievements": config_accessor().kinds_without_achievements,
        }
        return render_template("settings/kinds-without-achievements.html.j2", **context)

    @blueprint.route("/metadata-extraction", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def metadata_extraction():
        if request.method == "POST":
            metadata_extraction_regexes = request.form.getlist("regex")
            new_metadata_extraction_regexes = []
            for regex in metadata_extraction_regexes:
                try:
                    re.compile(regex)
                except re.error as e:
                    flash(
                        f"Cannot parse regex {regex} due to error: {e}",
                        category="danger",
                    )
                else:
                    new_metadata_extraction_regexes.append(regex)

            config_accessor().metadata_extraction_regexes = (
                new_metadata_extraction_regexes
            )
            config_accessor.save()
            flash("Updated metadata extraction settings.", category="success")
        context = {
            "metadata_extraction_regexes": config_accessor().metadata_extraction_regexes,
        }
        return render_template("settings/metadata-extraction.html.j2", **context)

    @blueprint.route("/privacy-zones", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def privacy_zones():
        if request.method == "POST":
            zone_names = request.form.getlist("zone_name")
            zone_geojsons = request.form.getlist("zone_geojson")
            strava_login_helper.save_privacy_zones(zone_names, zone_geojsons)

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

            config_accessor().privacy_zones = new_zone_config
            config_accessor.save()
            flash("Updated privacy zones.", category="success")

        context = {
            "privacy_zones": {
                name: _wrap_coordinates(coordinates)
                for name, coordinates in config_accessor().privacy_zones.items()
            }
        }
        return render_template("settings/privacy-zones.html.j2", **context)

    @blueprint.route("/segmentation", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def segmentation():
        if request.method == "POST":
            threshold = int(request.form.get("threshold", 0))
            config_accessor().time_diff_threshold_seconds = threshold
            config_accessor.save()
            flash(f"Threshold set to {threshold}.", category="success")
            shutil.rmtree(_activity_enriched_dir)
            return redirect(url_for("upload.reload"))
        return render_template(
            "settings/segmentation.html.j2",
            threshold=config_accessor().time_diff_threshold_seconds,
        )

    @blueprint.route("/sharepic", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def sharepic():
        if request.method == "POST":
            names = request.form.getlist("name")
            config_accessor().sharepic_suppressed_fields = list(
                set(SHAREPIC_FIELDS) - set(names)
            )
            config_accessor.save()
            flash("Updated sharepic preferences.", category="success")
        return render_template(
            "settings/sharepic.html.j2",
            names=[
                (
                    name,
                    label,
                    name not in config_accessor().sharepic_suppressed_fields,
                )
                for name, label in SHAREPIC_FIELDS.items()
            ],
        )

    @blueprint.route("/strava", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def strava():
        if request.method == "POST":
            strava_client_id = request.form["strava_client_id"]
            strava_client_secret = request.form["strava_client_secret"]
            url = strava_login_helper.save_strava(
                strava_client_id, strava_client_secret
            )
            return redirect(url)
        return render_template(
            "settings/strava.html.j2", **strava_login_helper.render_strava()
        )

    @blueprint.route("/strava-callback")
    @needs_authentication(authenticator)
    def strava_callback():
        code = request.args.get("code", type=str)
        strava_login_helper.save_strava_code(code)
        return redirect(url_for(".strava"))

    return blueprint


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


class StravaLoginHelper:
    def __init__(self, config_accessor: ConfigAccessor) -> None:
        self._config_accessor = config_accessor

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
