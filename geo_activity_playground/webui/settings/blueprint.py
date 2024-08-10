from typing import Optional

from flask import Blueprint
from flask import flash
from flask import render_template
from flask import request

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

    return blueprint
