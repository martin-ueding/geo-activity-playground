import json
import re
import urllib.parse
from typing import Any
from typing import Optional

import sqlalchemy
from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for
from tqdm import tqdm

from ...core.config import Config
from ...core.config import ConfigAccessor
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.datamodel import Equipment
from ...core.datamodel import ExplorerTileBookmark
from ...core.datamodel import Kind
from ...core.datamodel import Tag
from ...core.enrichment import update_and_commit
from ...core.heart_rate import HeartRateZoneComputer
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes
from ..i18n import SUPPORTED_LANGUAGES

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

    @blueprint.route("/language", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def language():
        if request.method == "POST":
            lang = request.form.get("language", "")
            if lang:
                config_accessor().preferred_language = lang
                flasher.flash_message(
                    "Language preference updated.", FlashTypes.SUCCESS
                )
            else:
                # Empty string means "Auto"
                config_accessor().preferred_language = None
                flasher.flash_message(
                    "Language preference cleared. Using browser language.",
                    FlashTypes.SUCCESS,
                )
            config_accessor.save()
            # Redirect to refresh the page with new language
            return redirect(url_for("settings.language"))

        current_language = config_accessor().preferred_language or ""
        return render_template(
            "settings/language.html.j2",
            available_languages=SUPPORTED_LANGUAGES,
            current_language=current_language,
        )

    @blueprint.route("/admin-password", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def admin_password() -> Response:
        if request.method == "POST":
            config_accessor().upload_password = request.form["password"]
            config_accessor.save()
            flasher.flash_message("Updated admin password.", FlashTypes.SUCCESS)
        return Response(
            render_template(
                "settings/admin-password.html.j2",
                password=config_accessor().upload_password,
            )
        )

    @blueprint.route("/cluster-bookmarks/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def cluster_bookmark_new():
        if request.method == "POST":
            bm = ExplorerTileBookmark(
                name=request.form["name"],
                zoom=int(request.form["zoom"]),
                tile_x=int(request.form["tile_x"]),
                tile_y=int(request.form["tile_y"]),
            )
            DB.session.add(bm)
            DB.session.commit()
            return redirect(
                url_for("explorer.server_side", zoom=int(request.form["zoom"]))
            )
        else:
            return render_template(
                "settings/cluster-bookmarks-new.html.j2",
                zoom=request.args["zoom"],
                tile_x=request.args["tile_x"],
                tile_y=request.args["tile_y"],
            )

    @blueprint.route("/cluster-bookmarks/delete/<int:id>")
    @needs_authentication(authenticator)
    def cluster_bookmark_delete(id: int):
        bookmark = DB.session.get_one(ExplorerTileBookmark, id)
        flasher.flash_message(f"Bookmark {bookmark.name} deleted.", FlashTypes.SUCCESS)
        DB.session.delete(bookmark)
        DB.session.commit()
        return redirect(request.referrer)

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

    @blueprint.route("/color-strategy", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def color_strategy():
        if request.method == "POST":
            print(request.form)
            config_accessor().color_strategy_max_cluster_color = _combine_color(
                request.form["max_cluster_color"],
                int(request.form["max_cluster_color_alpha"]),
            )
            config_accessor().color_strategy_max_cluster_other_color = _combine_color(
                request.form["max_cluster_other_color"],
                int(request.form["max_cluster_other_color_alpha"]),
            )
            config_accessor().color_strategy_visited_color = _combine_color(
                request.form["visited_color"], int(request.form["visited_color_alpha"])
            )
            config_accessor().color_strategy_cmap_opacity = float(
                request.form["cmap_opacity"]
            )
            config_accessor.save()
            flash("Updated color strategy values.", category="success")

        new_config = Config()
        max_cluster_color, max_cluster_color_alpha = _split_hex_into_color_alpha(
            config_accessor().color_strategy_max_cluster_color
        )
        max_cluster_color_default, max_cluster_color_alpha_default = (
            _split_hex_into_color_alpha(new_config.color_strategy_max_cluster_color)
        )

        max_cluster_other_color, max_cluster_other_color_alpha = (
            _split_hex_into_color_alpha(
                config_accessor().color_strategy_max_cluster_other_color
            )
        )
        max_cluster_other_color_default, max_cluster_other_color_alpha_default = (
            _split_hex_into_color_alpha(
                new_config.color_strategy_max_cluster_other_color
            )
        )

        visited_color, visited_color_alpha = _split_hex_into_color_alpha(
            config_accessor().color_strategy_visited_color
        )
        visited_color_default, visited_color_alpha_default = (
            _split_hex_into_color_alpha(new_config.color_strategy_visited_color)
        )

        return render_template(
            "settings/color-strategy.html.j2",
            max_cluster_color=max_cluster_color,
            max_cluster_color_default=max_cluster_color_default,
            max_cluster_color_alpha=max_cluster_color_alpha,
            max_cluster_color_alpha_default=max_cluster_color_alpha_default,
            max_cluster_other_color=max_cluster_other_color,
            max_cluster_other_color_default=max_cluster_other_color_default,
            max_cluster_other_color_alpha=max_cluster_other_color_alpha,
            max_cluster_other_color_alpha_default=max_cluster_other_color_alpha_default,
            visited_color=visited_color,
            visited_color_default=visited_color_default,
            visited_color_alpha=visited_color_alpha,
            visited_color_alpha_default=visited_color_alpha_default,
            cmap_opacity=config_accessor().color_strategy_cmap_opacity,
        )

    @blueprint.route("/manage-equipments", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def manage_equipments():
        if request.method == "POST":
            ids = request.form.getlist("id")
            names = request.form.getlist("name")
            offsets = request.form.getlist("offset_km")
            assert len(ids) == len(names) == len(offsets)
            for id, name, offset in zip(ids, names, offsets):
                if id:
                    equipment = DB.session.get_one(Equipment, int(id))
                    equipment.name = name
                    equipment.offset_km = int(float(offset))
                if not id and name:
                    equipment = Equipment(name=name)
                    if offset:
                        equipment.offset_km = int(float(offset))
                    DB.session.add(equipment)
                    flasher.flash_message(
                        f"Equipment '{name}' added.", FlashTypes.SUCCESS
                    )
            DB.session.commit()
        equipments = DB.session.scalars(
            sqlalchemy.select(Equipment).order_by(Equipment.name)
        ).all()
        return render_template(
            "settings/manage-equipments.html.j2",
            equipments=equipments,
        )

    @blueprint.route("/manage-kinds")
    @needs_authentication(authenticator)
    def manage_kinds():
        kinds = DB.session.scalars(sqlalchemy.select(Kind).order_by(Kind.name)).all()
        return render_template(
            "settings/kinds-list.html.j2",
            kinds=kinds,
        )

    @blueprint.route("/manage-kinds/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def kinds_new():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flasher.flash_message("Kind name is required.", FlashTypes.DANGER)
                return redirect(url_for(".kinds_new"))

            consider_for_achievements = (
                request.form.get("consider_for_achievements") == "on"
            )
            default_equipment_id = request.form.get("default_equipment_id")
            default_equipment_id = (
                int(default_equipment_id) if default_equipment_id else None
            )
            replaced_by_id = request.form.get("replaced_by_id")
            replaced_by_id = int(replaced_by_id) if replaced_by_id else None

            kind = Kind(name=name, consider_for_achievements=consider_for_achievements)
            if default_equipment_id:
                kind.default_equipment_id = default_equipment_id
            if replaced_by_id:
                kind.replaced_by_id = replaced_by_id

            DB.session.add(kind)
            DB.session.commit()
            flasher.flash_message(f"Kind '{name}' added.", FlashTypes.SUCCESS)
            return redirect(url_for(".manage_kinds"))

        kinds = DB.session.scalars(sqlalchemy.select(Kind).order_by(Kind.name)).all()
        equipments = DB.session.scalars(
            sqlalchemy.select(Equipment).order_by(Equipment.name)
        ).all()
        return render_template(
            "settings/kinds-new.html.j2",
            kinds=kinds,
            equipments=equipments,
        )

    @blueprint.route("/manage-kinds/edit/<int:id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def kinds_edit(id: int):
        kind = DB.session.get_one(Kind, id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flasher.flash_message("Kind name is required.", FlashTypes.DANGER)
                return redirect(url_for(".kinds_edit", id=id))

            consider_for_achievements = (
                request.form.get("consider_for_achievements") == "on"
            )
            default_equipment_id = request.form.get("default_equipment_id")
            default_equipment_id = (
                int(default_equipment_id) if default_equipment_id else None
            )
            replaced_by_id = request.form.get("replaced_by_id")
            replaced_by_id = int(replaced_by_id) if replaced_by_id else None

            if replaced_by_id is not None:
                replaced_by = DB.session.get_one(Kind, replaced_by_id)
                if replaced_by.replaced_by is not None:
                    flasher.flash_message(
                        f"Cannot set “{kind.name}” to be replaced by “{replaced_by.name}” as the latter is already replaced by something else.",
                        FlashTypes.DANGER,
                    )
                    replaced_by_id = None

            # Update kind
            kind.name = name
            kind.consider_for_achievements = consider_for_achievements
            kind.default_equipment_id = default_equipment_id
            old_replaced_by_id = kind.replaced_by_id
            kind.replaced_by_id = replaced_by_id

            # Migrate activities if replaced_by changed.
            if old_replaced_by_id != replaced_by_id:
                if kind.replaced_by is not None:
                    canonical_kind = kind.replaced_by
                    activities_to_migrate = DB.session.scalars(
                        sqlalchemy.select(Activity).where(Activity.kind_id == id)
                    ).all()
                    count = len(activities_to_migrate)
                    for activity in activities_to_migrate:
                        activity.kind_id = canonical_kind.id
                    if count:
                        flasher.flash_message(
                            f"Migrated {count} activities from '{kind.name}' to '{canonical_kind.name}'.",
                            FlashTypes.SUCCESS,
                        )

            DB.session.commit()
            flasher.flash_message(f"Kind “{name}” updated.", FlashTypes.SUCCESS)
            return redirect(url_for(".manage_kinds"))

        kinds = DB.session.scalars(sqlalchemy.select(Kind).order_by(Kind.name)).all()
        equipments = DB.session.scalars(
            sqlalchemy.select(Equipment).order_by(Equipment.name)
        ).all()
        return render_template(
            "settings/kinds-edit.html.j2",
            kind=kind,
            kinds=kinds,
            equipments=equipments,
        )

    @blueprint.route("/manage-kinds/delete/<int:id>")
    @needs_authentication(authenticator)
    def kinds_delete(id: int):
        kind = DB.session.get_one(Kind, id)
        kind_name = kind.name
        DB.session.delete(kind)
        DB.session.commit()
        flasher.flash_message(f"Kind '{kind_name}' deleted.", FlashTypes.SUCCESS)
        return redirect(url_for(".manage_kinds"))

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
            save_privacy_zones(zone_names, zone_geojsons, config_accessor)

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
            for activity in tqdm(
                DB.session.scalars(sqlalchemy.select(Activity)).all(),
                desc="Recomputing segments",
            ):
                time_series = activity.time_series
                update_and_commit(activity, time_series, config_accessor())
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
        assert code
        strava_login_helper.save_strava_code(code)
        return redirect(url_for(".strava"))

    @blueprint.route("/tags")
    @needs_authentication(authenticator)
    def tags_list():
        return render_template(
            "settings/tags-list.html.j2",
            tags=DB.session.scalars(sqlalchemy.select(Tag)).all(),
        )

    @blueprint.route("/tags/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tags_new():
        if request.method == "POST":
            tag_str = request.form["tag"]
            tag = Tag(tag=tag_str)
            DB.session.add(tag)
            DB.session.commit()
            return redirect(url_for(".tags_list"))
        else:
            return render_template("settings/tags-new.html.j2")

    @blueprint.route("/tags/edit/<int:id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tags_edit(id: int):
        tag = DB.session.get_one(Tag, id)
        if request.method == "POST":
            tag.tag = request.form["tag"]
            tag.color = request.form["color"]
            DB.session.commit()
            return redirect(url_for(".tags_list"))
        else:
            return render_template("settings/tags-edit.html.j2", tag=tag)

    @blueprint.route("/tile-source", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tile_source() -> str:
        if request.method == "POST":
            config_accessor().map_tile_url = request.form["map_tile_url"]
            config_accessor().map_tile_attribution = request.form[
                "map_tile_attribution"
            ]
            config_accessor.save()
            flasher.flash_message("Tile source updated.", FlashTypes.SUCCESS)
        return render_template(
            "settings/tile-source.html.j2",
            map_tile_url=config_accessor().map_tile_url,
            map_tile_attribution=config_accessor().map_tile_attribution,
            test_url=config_accessor().map_tile_url.format(zoom=14, x=8514, y=5504),
        )

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


def save_privacy_zones(
    zone_names: list[str], zone_geojsons: list[str], config_accessor: ConfigAccessor
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

    config_accessor().privacy_zones = new_zone_config
    config_accessor.save()
    flash("Updated privacy zones.", category="success")


def _add_alpha_if_needed(color_str: str) -> str:
    if 6 <= len(color_str) <= 7:
        color_str += "4d"
    if len(color_str) == 7:
        color_str = "#" + color_str
    return color_str


def _split_hex_into_color_alpha(color_str: str) -> tuple[str, int]:
    return color_str[:7], int(color_str[7:9], base=16)


def _combine_color(color: str, alpha: int) -> str:
    return f"{color}{alpha:02x}"
