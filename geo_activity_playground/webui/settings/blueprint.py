from typing import Optional

from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.webui.settings.controller import SettingsController


def int_or_none(s: str) -> Optional[int]:
    if s:
        try:
            return int(s)
        except ValueError as e:
            flash(f"Cannot parse integer from {s}: {e}", category="danger")


def make_settings_blueprint(config_accessor: ConfigAccessor) -> Blueprint:
    settings_controller = SettingsController(config_accessor)
    blueprint = Blueprint("settings", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        return render_template("settings/index.html.j2")

    @blueprint.route("/equipment-offsets", methods=["GET", "POST"])
    def equipment_offsets():
        if request.method == "POST":
            equipments = request.form.getlist("equipment")
            offsets = request.form.getlist("offset")
            settings_controller.save_equipment_offsets(equipments, offsets)
        return render_template(
            "settings/equipment-offsets.html.j2",
            **settings_controller.render_equipment_offsets(),
        )

    @blueprint.route("/heart-rate", methods=["GET", "POST"])
    def heart_rate():
        if request.method == "POST":
            birth_year = int_or_none(request.form["birth_year"])
            heart_rate_resting = int_or_none(request.form["heart_rate_resting"])
            if heart_rate_resting is None:
                heart_rate_resting = 0
            heart_rate_maximum = int_or_none(request.form["heart_rate_maximum"])
            settings_controller.save_heart_rate(
                birth_year, heart_rate_resting, heart_rate_maximum
            )
        return render_template(
            "settings/heart-rate.html.j2", **settings_controller.render_heart_rate()
        )

    @blueprint.route("/kinds-without-achievements", methods=["GET", "POST"])
    def kinds_without_achievements():
        if request.method == "POST":
            kinds = request.form.getlist("kind")
            settings_controller.save_kinds_without_achievements(kinds)
        return render_template(
            "settings/kinds-without-achievements.html.j2",
            **settings_controller.render_kinds_without_achievements(),
        )

    @blueprint.route("/metadata-extraction", methods=["GET", "POST"])
    def metadata_extraction():
        if request.method == "POST":
            regexes = request.form.getlist("regex")
            settings_controller.save_metadata_extraction(regexes)
        return render_template(
            "settings/metadata-extraction.html.j2",
            **settings_controller.render_metadata_extraction(),
        )

    @blueprint.route("/privacy-zones", methods=["GET", "POST"])
    def privacy_zones():
        if request.method == "POST":
            zone_names = request.form.getlist("zone_name")
            zone_geojsons = request.form.getlist("zone_geojson")
            settings_controller.save_privacy_zones(zone_names, zone_geojsons)
        return render_template(
            "settings/privacy-zones.html.j2",
            **settings_controller.render_privacy_zones(),
        )

    @blueprint.route("/strava", methods=["GET", "POST"])
    def strava():
        if request.method == "POST":
            strava_client_id = request.form["strava_client_id"]
            strava_client_secret = request.form["strava_client_secret"]
            url = settings_controller.save_strava(
                strava_client_id, strava_client_secret
            )
            return redirect(url)
        return render_template(
            "settings/strava.html.j2", **settings_controller.render_strava()
        )

    @blueprint.route("/strava-callback")
    def strava_callback():
        code = request.args.get("code", type=str)
        settings_controller.save_strava_code(code)
        return redirect(url_for(".strava"))

    return blueprint
