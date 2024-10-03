from typing import Optional

from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.webui.authenticator import Authenticator
from geo_activity_playground.webui.authenticator import needs_authentication
from geo_activity_playground.webui.settings.controller import SettingsController


def int_or_none(s: str) -> Optional[int]:
    if s:
        try:
            return int(s)
        except ValueError as e:
            flash(f"Cannot parse integer from {s}: {e}", category="danger")
    else:
        return None


def make_settings_blueprint(
    config_accessor: ConfigAccessor, authenticator: Authenticator
) -> Blueprint:
    settings_controller = SettingsController(config_accessor)
    blueprint = Blueprint("settings", __name__, template_folder="templates")

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        return render_template("settings/index.html.j2")

    @blueprint.route("/admin-password", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def admin_password():
        if request.method == "POST":
            settings_controller.save_admin_password(request.form["password"])
        return render_template(
            "settings/admin-password.html.j2",
            **settings_controller.render_admin_password(),
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
            config_accessor.save()
            flash("Updated color schemes.", category="success")
        return render_template(
            "settings/color-schemes.html.j2",
            color_scheme_for_counts=config_accessor().color_scheme_for_counts,
            color_scheme_for_counts_avail=[
                "viridis",
                "magma",
                "inferno",
                "plasma",
                "cividis",
                "turbo",
                "bluegreen",
                "bluepurple",
                "goldgreen",
                "goldorange",
                "goldred",
                "greenblue",
                "orangered",
                "purplebluegreen",
                "purpleblue",
                "purplered",
                "redpurple",
                "yellowgreenblue",
                "yellowgreen",
                "yelloworangebrown",
                "yelloworangered",
                "darkblue",
                "darkgold",
                "darkgreen",
                "darkmulti",
                "darkred",
                "lightgreyred",
                "lightgreyteal",
                "lightmulti",
                "lightorange",
                "lighttealblue",
            ],
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
        )

    @blueprint.route("/equipment-offsets", methods=["GET", "POST"])
    @needs_authentication(authenticator)
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
    @needs_authentication(authenticator)
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
    @needs_authentication(authenticator)
    def kinds_without_achievements():
        if request.method == "POST":
            kinds = request.form.getlist("kind")
            settings_controller.save_kinds_without_achievements(kinds)
        return render_template(
            "settings/kinds-without-achievements.html.j2",
            **settings_controller.render_kinds_without_achievements(),
        )

    @blueprint.route("/metadata-extraction", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def metadata_extraction():
        if request.method == "POST":
            regexes = request.form.getlist("regex")
            settings_controller.save_metadata_extraction(regexes)
        return render_template(
            "settings/metadata-extraction.html.j2",
            **settings_controller.render_metadata_extraction(),
        )

    @blueprint.route("/privacy-zones", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def privacy_zones():
        if request.method == "POST":
            zone_names = request.form.getlist("zone_name")
            zone_geojsons = request.form.getlist("zone_geojson")
            settings_controller.save_privacy_zones(zone_names, zone_geojsons)
        return render_template(
            "settings/privacy-zones.html.j2",
            **settings_controller.render_privacy_zones(),
        )

    @blueprint.route("/sharepic", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def sharepic():
        if request.method == "POST":
            names = request.form.getlist("name")
            settings_controller.save_sharepic(names)
        return render_template(
            "settings/sharepic.html.j2",
            **settings_controller.render_sharepic(),
        )

    @blueprint.route("/strava", methods=["GET", "POST"])
    @needs_authentication(authenticator)
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
    @needs_authentication(authenticator)
    def strava_callback():
        code = request.args.get("code", type=str)
        settings_controller.save_strava_code(code)
        return redirect(url_for(".strava"))

    return blueprint
