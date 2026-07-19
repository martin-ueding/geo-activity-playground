import json
import logging
import pathlib
import re
import shutil
from typing import Any

import sqlalchemy
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from tqdm import tqdm

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import (
    DB,
    Activity,
    ActivityImportConfig,
    ActivityTile,
    ClusterHistoryCheckpoint,
    ClusterHistoryEvent,
    ClusterMembership,
    Equipment,
    ExplorerTileBookmark,
    Kind,
    PrivacyZone,
    StoredSearchQuery,
    Tag,
    TileVisit,
    UiConfig,
    activity_tag_association_table,
    get_or_make_equipment,
    get_or_make_kind,
)
from ...core.enrichment import enrichment_set_timezone, update_and_commit
from ...core.heart_rate import HeartRateZoneComputer
from ...core.tag_extraction import apply_tag_extraction, get_tags_with_extraction_regex
from ...explorer.tile_visits import (
    _reset_tile_visits_db,
    compute_tile_evolution,
    compute_tile_visits_new,
)
from ...features.activity_photos.model import Photo
from ...features.hammerhead.blueprint import register_hammerhead_settings
from ...features.heatmap.blueprint import register_heatmap_settings
from ...features.heatmap.model import HeatmapTileCache
from ...features.plot_builder.model import PlotSpec
from ...features.segments.model import Segment, SegmentCheck, SegmentMatch
from ...features.square_planner.model import SquarePlannerBookmark
from ...features.strava_api.blueprint import register_strava_api_settings
from ...features.strava_api.importer import refresh_activity_names_from_strava
from ...features.strava_checkout.blueprint import register_strava_checkout_settings
from ...importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
    read_activity,
)
from ...importers.directory import get_metadata_from_path
from ..authenticator import Authenticator, needs_authentication
from ..columns import TOGGLEABLE_TABLE_COLUMNS
from ..flasher import Flasher, FlashTypes
from ..i18n import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

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


def int_or_none(s: str) -> int | None:
    if s:
        try:
            return int(s)
        except ValueError as e:
            flash(f"Cannot parse integer from {s}: {e}", category="danger")
    return None


def _ui_config_default(field: str):
    """Return the column default declared on ``UiConfig`` for display placeholders."""
    return UiConfig.__table__.c[field].default.arg


def _reprocess_all_activities(
    config: ActivityImportConfig,
    *,
    force: bool,
    use_raw_time_series: bool,
    desc: str,
) -> None:
    for activity in tqdm(
        DB.session.scalars(sqlalchemy.select(Activity)).all(),
        desc=desc,
    ):
        time_series = (
            activity.raw_time_series if use_raw_time_series else activity.time_series
        )
        update_and_commit(activity, time_series, config, force=force)


def _reimport_time_series_from_files(
    config: ActivityImportConfig,
) -> tuple[int, int, int]:
    activities = DB.session.scalars(
        sqlalchemy.select(Activity).filter(Activity.path.is_not(sqlalchemy.null()))
    ).all()
    reimported = skipped = errors = 0
    for activity in tqdm(activities, desc="Re-importing time series from files"):
        assert activity.path is not None
        path = pathlib.Path(activity.path)
        if not path.exists():
            logger.warning(f"Activity file not found, skipping: {path}")
            skipped += 1
            continue
        try:
            _, time_series = read_activity(path)
        except (ActivityParseError, NoGeoDataError) as e:
            logger.error(f"Could not parse {path}: {e}")
            errors += 1
            continue
        except Exception:
            logger.exception(f"Unexpected error parsing {path}")
            errors += 1
            continue
        update_and_commit(activity, time_series, config, force=True)
        reimported += 1
    return reimported, skipped, errors


def _truncate_user_content_tables() -> None:
    DB.session.execute(sqlalchemy.delete(activity_tag_association_table))
    DB.session.execute(sqlalchemy.delete(SegmentMatch))
    DB.session.execute(sqlalchemy.delete(SegmentCheck))
    DB.session.execute(sqlalchemy.delete(ActivityTile))
    DB.session.execute(sqlalchemy.delete(TileVisit))
    DB.session.execute(sqlalchemy.delete(ClusterHistoryEvent))
    DB.session.execute(sqlalchemy.delete(ClusterHistoryCheckpoint))
    DB.session.execute(sqlalchemy.delete(ClusterMembership))
    DB.session.execute(sqlalchemy.delete(Photo))
    DB.session.execute(sqlalchemy.delete(Activity))
    DB.session.execute(sqlalchemy.delete(Segment))
    DB.session.execute(sqlalchemy.delete(Tag))
    DB.session.execute(sqlalchemy.delete(ExplorerTileBookmark))
    DB.session.execute(sqlalchemy.delete(SquarePlannerBookmark))
    DB.session.execute(sqlalchemy.delete(PlotSpec))
    DB.session.execute(sqlalchemy.delete(HeatmapTileCache))
    DB.session.execute(sqlalchemy.delete(StoredSearchQuery))
    DB.session.commit()


def _wipe_local_state() -> None:
    _truncate_user_content_tables()

    for directory in [
        pathlib.Path("Cache"),
        pathlib.Path("Time Series"),
        pathlib.Path("Photos"),
    ]:
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)


def _apply_metadata_extraction_to_existing(config: ActivityImportConfig) -> int:
    activities = DB.session.scalars(
        sqlalchemy.select(Activity).filter(Activity.path.is_not(sqlalchemy.null()))
    ).all()
    changed = 0
    for activity in activities:
        assert activity.path is not None
        meta = get_metadata_from_path(
            pathlib.Path(activity.path), config.metadata_extraction_regexes
        )
        if not meta:
            continue
        if "name" in meta:
            activity.name = meta["name"]
        if "kind" in meta:
            activity.kind = get_or_make_kind(meta["kind"])
        if "equipment" in meta:
            activity.equipment = get_or_make_equipment(meta["equipment"], config)
        changed += 1
    DB.session.commit()
    return changed


def make_settings_blueprint(
    config_accessor: ConfigAccessor,
    authenticator: Authenticator,
    flasher: Flasher,
    repository: ActivityRepository,
) -> Blueprint:
    blueprint = Blueprint("settings", __name__, template_folder="templates")
    register_hammerhead_settings(blueprint, authenticator)
    register_heatmap_settings(blueprint, authenticator, flasher)
    register_strava_api_settings(blueprint, authenticator, config_accessor)
    register_strava_checkout_settings(blueprint, authenticator, flasher)

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        return render_template("settings/index.html.j2")

    @blueprint.route("/maintenance", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def maintenance():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "reset_tile_visit_state":
                logger.info("User requested reset of tile visit state.")
                _reset_tile_visits_db()
                compute_tile_visits_new(repository)
                compute_tile_evolution(config_accessor.ui())
                flasher.flash_message(
                    _("Tile visit state has been reset and re-indexed."),
                    FlashTypes.SUCCESS,
                )
            elif action == "reenrich_all_activities":
                logger.info("User requested re-enrichment of all activities.")
                _reprocess_all_activities(
                    config_accessor.activity_import(),
                    force=True,
                    use_raw_time_series=True,
                    desc="Re-enriching activities",
                )
                flasher.flash_message(
                    _("All activities have been re-enriched."),
                    FlashTypes.SUCCESS,
                )
            elif action == "repair_activities":
                logger.info("User requested repair of activities.")
                _reprocess_all_activities(
                    config_accessor.activity_import(),
                    force=True,
                    use_raw_time_series=True,
                    desc="Repairing activities",
                )
                flasher.flash_message(
                    _("Activities have been repaired and reprocessed."),
                    FlashTypes.SUCCESS,
                )
            elif action == "wipe_local_state":
                logger.info("User requested wipe of local activity state.")
                _wipe_local_state()
                flasher.flash_message(
                    _(
                        "Local activity state has been wiped. Equipment, kinds, and Strava API credentials were preserved."
                    ),
                    FlashTypes.SUCCESS,
                )
            elif action == "refresh_strava_activity_names":
                logger.info("User requested Strava activity name refresh.")
                updated_names = refresh_activity_names_from_strava(
                    config_accessor.strava()
                )
                flasher.flash_message(
                    _(
                        "Refreshed activity names from Strava. Updated %(updated_names)s activities."
                    )
                    % {"updated_names": updated_names},
                    FlashTypes.SUCCESS,
                )
            elif action == "reimport_time_series_from_files":
                logger.info(
                    "User requested re-import of time series from activity files."
                )
                reimported, skipped, errors = _reimport_time_series_from_files(
                    config_accessor.activity_import()
                )
                flasher.flash_message(
                    _(
                        "Re-imported time series from activity files: %(reimported)s re-imported, %(skipped)s skipped (file missing), %(errors)s errors."
                    )
                    % {
                        "reimported": reimported,
                        "skipped": skipped,
                        "errors": errors,
                    },
                    FlashTypes.SUCCESS,
                )
            elif action in ("fix_timezone_local_to_utc", "fix_timezone_utc_to_utc"):
                from_iana = action == "fix_timezone_local_to_utc"
                logger.info("User requested timezone fix (from_iana=%s).", from_iana)
                config = config_accessor.activity_import()
                for activity in DB.session.scalars(sqlalchemy.select(Activity)).all():
                    if activity.start is None:
                        continue
                    time_series = activity.raw_time_series
                    enrichment_set_timezone(activity, time_series, config)
                    if time_series["time"].dt.tz is None:
                        time_series["time"] = time_series["time"].dt.tz_localize(
                            activity.iana_timezone if from_iana else "UTC"
                        )
                    time_series["time"] = time_series["time"].dt.tz_convert("UTC")
                    update_and_commit(activity, time_series, config)
                flasher.flash_message(
                    _("Activity timezones have been fixed."),
                    FlashTypes.SUCCESS,
                )
            return redirect(url_for(".maintenance"))
        return render_template("settings/maintenance.html.j2")

    @blueprint.route("/language", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def language():
        if request.method == "POST":
            lang = request.form.get("language", "")
            if lang:
                config_accessor.ui().preferred_language = lang
                flasher.flash_message(
                    "Language preference updated.", FlashTypes.SUCCESS
                )
            else:
                # Empty string means "Auto"
                config_accessor.ui().preferred_language = None
                flasher.flash_message(
                    "Language preference cleared. Using browser language.",
                    FlashTypes.SUCCESS,
                )
            config_accessor.save()
            # Redirect to refresh the page with new language
            return redirect(url_for("settings.language"))

        current_language = config_accessor.ui().preferred_language or ""
        return render_template(
            "settings/language.html.j2",
            available_languages=SUPPORTED_LANGUAGES,
            current_language=current_language,
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
            config_accessor.ui().color_scheme_for_counts = request.form[
                "color_scheme_for_counts"
            ]
            config_accessor.ui().color_scheme_for_kind = request.form[
                "color_scheme_for_kind"
            ]
            config_accessor.ui().color_scheme_for_heatmap = request.form[
                "color_scheme_for_heatmap"
            ]
            config_accessor.save()
            flash("Updated color schemes.", category="success")

        return render_template(
            "settings/color-schemes.html.j2",
            color_scheme_for_counts=config_accessor.ui().color_scheme_for_counts,
            color_scheme_for_counts_avail=VEGA_COLOR_SCHEMES_CONTINUOUS,
            color_scheme_for_kind=config_accessor.ui().color_scheme_for_kind,
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
            color_scheme_for_heatmap=config_accessor.ui().color_scheme_for_heatmap,
            color_scheme_for_heatmap_avail=MATPLOTLIB_COLOR_SCHEMES_CONTINUOUS,
        )

    @blueprint.route("/color-strategy", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def color_strategy():
        if request.method == "POST":
            print(request.form)
            config_accessor.ui().color_strategy_max_cluster_color = _combine_color(
                request.form["max_cluster_color"],
                int(request.form["max_cluster_color_alpha"]),
            )
            config_accessor.ui().color_strategy_max_cluster_other_color = (
                _combine_color(
                    request.form["max_cluster_other_color"],
                    int(request.form["max_cluster_other_color_alpha"]),
                )
            )
            config_accessor.ui().color_strategy_visited_color = _combine_color(
                request.form["visited_color"], int(request.form["visited_color_alpha"])
            )
            config_accessor.ui().color_strategy_cmap_opacity = float(
                request.form["cmap_opacity"]
            )
            config_accessor.save()
            flash("Updated color strategy values.", category="success")

        max_cluster_color, max_cluster_color_alpha = _split_hex_into_color_alpha(
            config_accessor.ui().color_strategy_max_cluster_color
        )
        max_cluster_color_default, max_cluster_color_alpha_default = (
            _split_hex_into_color_alpha(
                _ui_config_default("color_strategy_max_cluster_color")
            )
        )

        max_cluster_other_color, max_cluster_other_color_alpha = (
            _split_hex_into_color_alpha(
                config_accessor.ui().color_strategy_max_cluster_other_color
            )
        )
        max_cluster_other_color_default, max_cluster_other_color_alpha_default = (
            _split_hex_into_color_alpha(
                _ui_config_default("color_strategy_max_cluster_other_color")
            )
        )

        visited_color, visited_color_alpha = _split_hex_into_color_alpha(
            config_accessor.ui().color_strategy_visited_color
        )
        visited_color_default, visited_color_alpha_default = (
            _split_hex_into_color_alpha(
                _ui_config_default("color_strategy_visited_color")
            )
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
            cmap_opacity=config_accessor.ui().color_strategy_cmap_opacity,
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
            config_accessor.heart_rate().birth_year = birth_year
            config_accessor.heart_rate().heart_rate_resting = heart_rate_resting or 0
            config_accessor.heart_rate().heart_rate_maximum = heart_rate_maximum
            config_accessor.save()
            flash("Updated heart rate data.", category="success")

        context: dict[str, Any] = {
            "birth_year": config_accessor.heart_rate().birth_year,
            "heart_rate_resting": config_accessor.heart_rate().heart_rate_resting,
            "heart_rate_maximum": config_accessor.heart_rate().heart_rate_maximum,
        }

        heart_rate_computer = HeartRateZoneComputer(config_accessor)
        try:
            context["zone_boundaries"] = heart_rate_computer.zone_boundaries()
        except RuntimeError:
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

            config_accessor.activity_import().metadata_extraction_regexes = (
                new_metadata_extraction_regexes
            )
            config_accessor.save()
            flash("Updated metadata extraction settings.", category="success")
        context = {
            "metadata_extraction_regexes": config_accessor.activity_import().metadata_extraction_regexes,
        }
        return render_template("settings/metadata-extraction.html.j2", **context)

    @blueprint.route("/metadata-extraction/apply-to-existing", methods=["POST"])
    @needs_authentication(authenticator)
    def metadata_extraction_apply_to_existing():
        changed = _apply_metadata_extraction_to_existing(
            config_accessor.activity_import()
        )
        flasher.flash_message(
            _(
                "Applied metadata extraction regexes to existing activities: %(changed)s updated."
            )
            % {"changed": changed},
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".metadata_extraction"))

    @blueprint.route("/privacy-zones", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def privacy_zones():
        if request.method == "POST":
            zone_names = request.form.getlist("zone_name")
            zone_geojsons = request.form.getlist("zone_geojson")
            save_privacy_zones(zone_names, zone_geojsons)
            flash("Updated privacy zones.", category="success")

        context = {
            "privacy_zones": {
                zone.name: _wrap_coordinates(zone.points)
                for zone in DB.session.scalars(
                    sqlalchemy.select(PrivacyZone).order_by(PrivacyZone.name)
                ).all()
            }
        }
        return render_template("settings/privacy-zones.html.j2", **context)

    @blueprint.route("/segmentation", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def segmentation():
        if request.method == "POST":
            threshold = int(request.form.get("threshold", 0))
            config_accessor.activity_import().time_diff_threshold_seconds = threshold
            config_accessor.save()
            flash(f"Threshold set to {threshold}.", category="success")
            _reprocess_all_activities(
                config_accessor.activity_import(),
                force=False,
                use_raw_time_series=True,
                desc="Recomputing segments",
            )
        return render_template(
            "settings/segmentation.html.j2",
            threshold=config_accessor.activity_import().time_diff_threshold_seconds,
        )

    @blueprint.route("/table-columns", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def table_columns():
        if request.method == "POST":
            names = request.form.getlist("name")
            known = {col.name for col in TOGGLEABLE_TABLE_COLUMNS}
            config_accessor.ui().visible_table_columns = [
                n for n in names if n in known
            ]
            config_accessor.save()
            flasher.flash_message(
                _("Updated summary table columns."), FlashTypes.SUCCESS
            )
        return render_template(
            "settings/table-columns.html.j2",
            columns=[
                (
                    col.name,
                    col.display_name,
                    col.name in config_accessor.ui().visible_table_columns,
                )
                for col in TOGGLEABLE_TABLE_COLUMNS
            ],
        )

    @blueprint.route("/map-display", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def map_display():
        if request.method == "POST":
            config_accessor.ui().show_progress_markers = (
                request.form.get("show_progress_markers") == "on"
            )
            config_accessor.save()
            flasher.flash_message(
                _("Updated map display preferences."), FlashTypes.SUCCESS
            )
        return render_template(
            "settings/map-display.html.j2",
            show_progress_markers=config_accessor.ui().show_progress_markers,
        )

    @blueprint.route("/sharepic", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def sharepic():
        if request.method == "POST":
            names = request.form.getlist("name")
            config_accessor.ui().sharepic_suppressed_fields = list(
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
                    name not in config_accessor.ui().sharepic_suppressed_fields,
                )
                for name, label in SHAREPIC_FIELDS.items()
            ],
        )

    @blueprint.route("/tags")
    @needs_authentication(authenticator)
    def tags_list():
        return render_template(
            "settings/tags-list.html.j2",
            tags=DB.session.scalars(sqlalchemy.select(Tag).order_by(Tag.tag)).all(),
        )

    @blueprint.route("/tags/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tags_new():
        if request.method == "POST":
            tag_str = request.form["tag"].strip()
            extraction_regex = request.form.get("extraction_regex", "").strip() or None
            extraction_destructive = request.form.get("extraction_destructive") == "on"
            color = request.form.get("color", "").strip() or None

            if extraction_regex is not None:
                try:
                    re.compile(extraction_regex)
                except re.error as e:
                    flasher.flash_message(
                        f"Cannot parse extraction regex due to error: {e}",
                        FlashTypes.DANGER,
                    )
                    return render_template(
                        "settings/tags-new.html.j2",
                        tag_value=tag_str,
                        color_value=color or "#0d6efd",
                        extraction_regex_value=extraction_regex or "",
                        extraction_destructive_value=extraction_destructive,
                    )

            tag = Tag(
                tag=tag_str,
                color=color,
                extraction_regex=extraction_regex,
                extraction_destructive=extraction_destructive,
            )
            DB.session.add(tag)
            DB.session.commit()
            return redirect(url_for(".tags_list"))
        else:
            return render_template(
                "settings/tags-new.html.j2",
                tag_value="",
                color_value="#0d6efd",
                extraction_regex_value="",
                extraction_destructive_value=False,
            )

    @blueprint.route("/tags/edit/<int:id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tags_edit(id: int):
        tag = DB.session.get_one(Tag, id)
        if request.method == "POST":
            new_extraction_regex = (
                request.form.get("extraction_regex", "").strip() or None
            )
            if new_extraction_regex is not None:
                try:
                    re.compile(new_extraction_regex)
                except re.error as e:
                    flasher.flash_message(
                        f"Cannot parse extraction regex due to error: {e}",
                        FlashTypes.DANGER,
                    )
                    return render_template("settings/tags-edit.html.j2", tag=tag)

            tag.tag = request.form["tag"]
            tag.color = request.form["color"]
            tag.extraction_regex = new_extraction_regex
            tag.extraction_destructive = (
                request.form.get("extraction_destructive") == "on"
            )
            DB.session.commit()
            return redirect(url_for(".tags_list"))
        else:
            return render_template("settings/tags-edit.html.j2", tag=tag)

    @blueprint.route("/tags/scan-existing", methods=["POST"])
    @needs_authentication(authenticator)
    def tags_scan_existing():
        tags = get_tags_with_extraction_regex()
        if not tags:
            flasher.flash_message(
                "There are no tags with extraction regex configured.",
                FlashTypes.WARNING,
            )
            return redirect(url_for(".tags_list"))

        activities = DB.session.scalars(
            sqlalchemy.select(Activity).order_by(Activity.id)
        ).all()
        changed = 0
        for activity in activities:
            if apply_tag_extraction(activity, tags):
                changed += 1
        DB.session.commit()
        flasher.flash_message(
            f"Scanned {len(activities)} activities and updated {changed}.",
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".tags_list"))

    @blueprint.route("/tile-source", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tile_source() -> str:
        if request.method == "POST":
            config_accessor.map().map_tile_url = request.form["map_tile_url"]
            config_accessor.map().map_tile_attribution = request.form[
                "map_tile_attribution"
            ]
            config_accessor.save()
            flasher.flash_message("Tile source updated.", FlashTypes.SUCCESS)
        return render_template(
            "settings/tile-source.html.j2",
            map_tile_url=config_accessor.map().map_tile_url,
            map_tile_attribution=config_accessor.map().map_tile_attribution,
            test_url=config_accessor.map().map_tile_url.format(zoom=14, x=8514, y=5504),
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


def save_privacy_zones(zone_names: list[str], zone_geojsons: list[str]) -> None:
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

    DB.session.execute(sqlalchemy.delete(PrivacyZone))
    for name, points in new_zone_config.items():
        DB.session.add(PrivacyZone(name=name, points=points))
    DB.session.commit()


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
