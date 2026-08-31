import datetime
import decimal
import json
import logging
import pathlib
import re
import shutil
from typing import Any

import babel.numbers
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

from ...core.config import ConfigAccessor
from ...core.currency import format_money
from ...core.datamodel import (
    DB,
    Activity,
    ActivityImportConfig,
    ActivityTile,
    DuplicateCandidate,
    Equipment,
    Kind,
    PrivacyZone,
    StoredSearchQuery,
    Tag,
    TileVisit,
    activity_tag_association_table,
)
from ...core.duplicate_matching import merge_duplicate, pick_winner
from ...core.enrichment import enrichment_set_timezone, update_and_commit
from ...core.heart_rate import HeartRateZoneComputer
from ...core.import_exclusion import ImportExclusion
from ...core.raster_map import (
    format_sample_tile_url,
    normalize_tile_url_template,
    probe_tile_url,
    tile_url_template_error,
)
from ...core.scan import refresh_stale_ingests
from ...core.tag_extraction import apply_tag_extraction, get_tags_with_extraction_regex
from ...core.tile_visits import (
    _reset_tile_visits_db,
    compute_tile_visits_new,
    rebuild_tile_visits_from_activity_tiles,
)
from ...features.activity_photos.model import Photo
from ...features.directory_import.blueprint import register_directory_import_settings
from ...features.explorer.clustering import (
    compute_current_state_for_zoom,
    compute_tile_evolution,
    delete_tile_evolution,
    mark_cluster_history_stale,
    rebuild_cluster_history,
)
from ...features.explorer.filtered import (
    delete_filtered_cluster_cache,
    delete_stale_filtered_cluster_cache,
    get_filtered_cluster_cache_stats,
)
from ...features.explorer.model import (
    TILE_STYLE_DEFAULTS,
    BorderStroke,
    ClusterHistoryEvent,
    ClusterMembership,
    ClusterTileActivation,
    ExplorerTileBookmark,
    FilteredClusterCache,
    TileStyleName,
    get_tile_styles,
)
from ...features.explorer.zoom_levels import (
    EXPLORER_ZOOM_LEVEL_NAMES,
    SELECTABLE_EXPLORER_ZOOM_LEVELS,
)
from ...features.hammerhead.blueprint import register_hammerhead_settings
from ...features.heatmap.blueprint import register_heatmap_settings
from ...features.heatmap.model import HeatmapTileCache
from ...features.plot_builder.model import PlotSpec
from ...features.segments.model import Segment, SegmentCheck, SegmentMatch
from ...features.square_planner.model import SquarePlannerBookmark
from ...features.strava.api_importer import refresh_activity_names_from_strava
from ...features.strava.blueprint import register_strava_settings
from ..authenticator import Authenticator, needs_authentication
from ..columns import TOGGLEABLE_TABLE_COLUMNS
from ..flasher import Flasher, FlashTypes
from ..i18n import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

HILLSHADE_BLEND_MODES = [
    "multiply",
    "screen",
    "overlay",
    "soft-light",
    "hard-light",
    "normal",
]

GRID_LINE_MIN_WIDTH_PX_OPTIONS = [16, 32, 64, 128, 256]
"""Explorer tile widths, in on-screen pixels, offered for the grid line threshold.

An explorer tile shrinks to half its width for each map zoom level you zoom
out, so these are the widths at which it would appear at all displayed zoom
levels; anything in between would never be reached exactly."""


def _import_exclusion_reasons() -> dict[str, str]:
    return {
        "no_geo_data": _("No geospatial data"),
        "parse_error": _("Parse error"),
        "empty_time_series": _("Empty time series"),
        "deleted_by_user": _("Deleted by user"),
        "merged_duplicate": _("Merged as a cross-source duplicate"),
    }


def _activity_source_labels() -> dict[str, str]:
    return {
        "directory": _("Directory / Manual Upload"),
        "strava": _("Strava"),
        "hammerhead": _("Hammerhead"),
    }


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


def _reparse_activities(config_accessor: ConfigAccessor) -> tuple[int, int]:
    """Read every activity again from the artifact its source kept.

    This is the ingest stage of the pipeline, run on demand rather than because a
    version stamp moved on. The file layer, the time series and every derived field
    are rebuilt from the source data; the user layer is not touched, so names, kinds,
    equipment and tags that were set by hand survive.
    """
    return refresh_stale_ingests(config_accessor, force=True)


def _truncate_user_content_tables() -> None:
    DB.session.execute(sqlalchemy.delete(activity_tag_association_table))
    DB.session.execute(sqlalchemy.delete(DuplicateCandidate))
    DB.session.execute(sqlalchemy.delete(SegmentMatch))
    DB.session.execute(sqlalchemy.delete(SegmentCheck))
    DB.session.execute(sqlalchemy.delete(ActivityTile))
    DB.session.execute(sqlalchemy.delete(TileVisit))
    DB.session.execute(sqlalchemy.delete(ClusterHistoryEvent))
    DB.session.execute(sqlalchemy.delete(ClusterTileActivation))
    DB.session.execute(sqlalchemy.delete(ClusterMembership))
    DB.session.execute(sqlalchemy.delete(FilteredClusterCache))
    DB.session.execute(sqlalchemy.delete(Photo))
    DB.session.execute(sqlalchemy.delete(Activity))
    DB.session.execute(sqlalchemy.delete(Segment))
    DB.session.execute(sqlalchemy.delete(Tag))
    DB.session.execute(sqlalchemy.delete(ExplorerTileBookmark))
    DB.session.execute(sqlalchemy.delete(SquarePlannerBookmark))
    DB.session.execute(sqlalchemy.delete(PlotSpec))
    DB.session.execute(sqlalchemy.delete(HeatmapTileCache))
    DB.session.execute(sqlalchemy.delete(StoredSearchQuery))
    DB.session.execute(sqlalchemy.delete(ImportExclusion))
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


def make_settings_blueprint(
    config_accessor: ConfigAccessor,
    authenticator: Authenticator,
    flasher: Flasher,
) -> Blueprint:
    blueprint = Blueprint("settings", __name__, template_folder="templates")
    register_directory_import_settings(
        blueprint, authenticator, flasher, config_accessor
    )
    register_hammerhead_settings(blueprint, authenticator)
    register_heatmap_settings(blueprint, authenticator, flasher)
    register_strava_settings(blueprint, authenticator, config_accessor, flasher)

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        return render_template("settings/index.html.j2")

    @blueprint.route("/excluded-activities")
    @needs_authentication(authenticator)
    def excluded_activities():
        exclusions = DB.session.scalars(
            sqlalchemy.select(ImportExclusion).order_by(
                ImportExclusion.last_attempt.desc()
            )
        ).all()
        return render_template(
            "settings/excluded-activities.html.j2",
            exclusions=exclusions,
            reasons=_import_exclusion_reasons(),
        )

    @blueprint.route("/excluded-activities/reimport/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def excluded_activity_reimport(id: int):
        exclusion = DB.session.get_one(ImportExclusion, id)
        DB.session.delete(exclusion)
        DB.session.commit()
        flasher.flash_message(
            _("The activity will be imported again on the next import scan."),
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".excluded_activities"))

    @blueprint.route("/excluded-activities/reimport-all", methods=["POST"])
    @needs_authentication(authenticator)
    def excluded_activities_reimport_all():
        count = DB.session.execute(
            sqlalchemy.delete(ImportExclusion).where(
                ImportExclusion.reason != "deleted_by_user"
            )
        ).rowcount
        DB.session.commit()
        flasher.flash_message(
            _(
                "Cleared %(count)s failed imports. They will be retried on the next import scan."
            )
            % {"count": count},
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".excluded_activities"))

    @blueprint.route("/duplicate-matching", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def duplicate_matching():
        config = config_accessor.activity_import()
        source_labels = _activity_source_labels()

        if request.method == "POST":
            config.duplicate_matching_enabled = request.form.get("enabled") == "on"
            config.duplicate_matching_auto_resolve = (
                request.form.get("auto_resolve") == "on"
            )
            time_tolerance = int_or_none(request.form.get("time_tolerance_seconds"))
            if time_tolerance is not None and time_tolerance >= 0:
                config.duplicate_time_tolerance_seconds = time_tolerance
            relative_tolerance = int_or_none(
                request.form.get("relative_tolerance_percent")
            )
            if relative_tolerance is not None and relative_tolerance >= 0:
                config.duplicate_relative_tolerance = relative_tolerance / 100

            priorities = dict(config.duplicate_source_priorities)
            for source in source_labels:
                priority = int_or_none(request.form.get(f"priority_{source}"))
                if priority is not None:
                    priorities[source] = priority
            config.duplicate_source_priorities = priorities

            config_accessor.save()
            flasher.flash_message(
                _("Updated duplicate matching settings."), FlashTypes.SUCCESS
            )
            return redirect(url_for(".duplicate_matching"))

        return render_template(
            "settings/duplicate-matching.html.j2",
            enabled=config.duplicate_matching_enabled,
            auto_resolve=config.duplicate_matching_auto_resolve,
            time_tolerance_seconds=config.duplicate_time_tolerance_seconds,
            relative_tolerance_percent=round(config.duplicate_relative_tolerance * 100),
            source_labels=source_labels,
            priorities=config.duplicate_source_priorities,
        )

    @blueprint.route("/possible-duplicates")
    @needs_authentication(authenticator)
    def possible_duplicates():
        config = config_accessor.activity_import()
        candidates = DB.session.scalars(
            sqlalchemy.select(DuplicateCandidate).order_by(
                DuplicateCandidate.detected_at.desc()
            )
        ).all()
        rows = []
        for candidate in candidates:
            suggested_winner = pick_winner(
                candidate.activity_a, candidate.activity_b, config
            )
            rows.append(
                {
                    "candidate": candidate,
                    "suggested_keep": (
                        "a"
                        if suggested_winner is candidate.activity_a
                        else "b"
                        if suggested_winner is candidate.activity_b
                        else None
                    ),
                }
            )
        return render_template(
            "settings/possible-duplicates.html.j2",
            rows=rows,
        )

    @blueprint.route("/possible-duplicates/resolve/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def possible_duplicates_resolve(id: int):
        candidate = DB.session.get_one(DuplicateCandidate, id)
        keep = request.form.get("keep")
        if keep == "a":
            winner, loser = candidate.activity_a, candidate.activity_b
        elif keep == "b":
            winner, loser = candidate.activity_b, candidate.activity_a
        else:
            flasher.flash_message(_("Invalid choice."), FlashTypes.DANGER)
            return redirect(url_for(".possible_duplicates"))
        merge_duplicate(winner, loser)
        flasher.flash_message(
            _("Merged the duplicate; the other activity has been removed."),
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".possible_duplicates"))

    @blueprint.route("/possible-duplicates/dismiss/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def possible_duplicates_dismiss(id: int):
        candidate = DB.session.get_one(DuplicateCandidate, id)
        DB.session.delete(candidate)
        DB.session.commit()
        flasher.flash_message(
            _(
                "Dismissed; these activities will not be flagged as duplicates of each other again unless re-imported."
            ),
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".possible_duplicates"))

    @blueprint.route("/maintenance", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def maintenance():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "reset_tile_visit_state":
                logger.info("User requested reset of tile visit state.")
                _reset_tile_visits_db()
                compute_tile_visits_new()
                compute_tile_evolution(config_accessor.ui())
                flasher.flash_message(
                    _("Tile visit state has been reset and re-indexed."),
                    FlashTypes.SUCCESS,
                )
            elif action == "clear_filtered_cluster_cache":
                logger.info("User requested reset of the filtered cluster cache.")
                dropped = delete_filtered_cluster_cache()
                flasher.flash_message(
                    _("Cleared %(dropped)s cached filtered cluster states.")
                    % {"dropped": dropped},
                    FlashTypes.SUCCESS,
                )
            elif action == "cleanup_filtered_cluster_cache_stale":
                logger.info("User requested cleanup of the filtered cluster cache.")
                cutoff = datetime.datetime.now() - datetime.timedelta(days=182)
                dropped = delete_stale_filtered_cluster_cache(cutoff)
                flasher.flash_message(
                    _(
                        "Dropped %(dropped)s cached filtered cluster states (unused for six months)."
                    )
                    % {"dropped": dropped},
                    FlashTypes.SUCCESS,
                )
            elif action == "rebuild_cluster_history":
                logger.info("User requested rebuild of the cluster history.")
                for zoom in config_accessor.ui().explorer_zoom_levels:
                    compute_current_state_for_zoom(zoom)
                    rebuild_cluster_history(zoom)
                flasher.flash_message(
                    _("The explorer tile history has been recomputed."),
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
            elif action == "reparse_activities":
                logger.info("User requested a re-parse of all activities.")
                reparsed, skipped = _reparse_activities(config_accessor)
                flasher.flash_message(
                    _(
                        "Re-parsed %(reparsed)s activities from their source data, %(skipped)s skipped because their source data is not available."
                    )
                    % {"reparsed": reparsed, "skipped": skipped},
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
        cache_count, cache_bytes = get_filtered_cluster_cache_stats()
        return render_template(
            "settings/maintenance.html.j2",
            filtered_cluster_cache_count=cache_count,
            filtered_cluster_cache_kib=round(cache_bytes / 1024),
        )

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

    @blueprint.route("/currency", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def currency():
        if request.method == "POST":
            code = request.form.get("currency", "").strip().upper()
            if code and code not in babel.numbers.list_currencies():
                flasher.flash_message(
                    _("'%(code)s' is not a known ISO 4217 currency code.", code=code),
                    FlashTypes.WARNING,
                )
            else:
                config_accessor.ui().currency = code
                config_accessor.save()
                flasher.flash_message(_("Currency updated."), FlashTypes.SUCCESS)
            return redirect(url_for(".currency"))

        return render_template(
            "settings/currency.html.j2",
            current_currency=config_accessor.ui().currency,
            example=format_money(
                decimal.Decimal("1234.5"), config_accessor.ui().currency
            ),
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

    @blueprint.route("/cluster-bookmarks/delete/<int:id>", methods=["POST"])
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

    @blueprint.route("/tile-rendering", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def tile_rendering():
        labels = {
            TileStyleName.VISITED: _("Visited"),
            TileStyleName.MISSING: _("Missing"),
            TileStyleName.NEW_TILE: _("New in this activity"),
            TileStyleName.NEW_TILE_NEW_CLUSTER: _(
                "New in this activity, joined a cluster"
            ),
            TileStyleName.VISITED_NEW_CLUSTER: _(
                "Visited before, joined a cluster in this activity"
            ),
            TileStyleName.MAX_CLUSTER: _("Part of max cluster"),
            TileStyleName.OTHER_CLUSTER: _("Part of other cluster"),
            TileStyleName.OLD_CLUSTER: _("Part of cluster before this activity"),
            TileStyleName.INACCESSIBLE: _("Inaccessible"),
        }
        groups = [
            (
                _("Tile state"),
                _(
                    "These roles mean the same thing in every color strategy that "
                    "uses them: whether a tile has been visited at all, is missing, "
                    "or was marked inaccessible."
                ),
                [
                    TileStyleName.VISITED,
                    TileStyleName.MISSING,
                    TileStyleName.INACCESSIBLE,
                ],
            ),
            (
                _("Cluster layer"),
                _(
                    "Used together by the “Max Cluster” color strategy to set apart "
                    "the largest cluster from the rest."
                ),
                [TileStyleName.MAX_CLUSTER, TileStyleName.OTHER_CLUSTER],
            ),
            (
                _("Activity highlight layer"),
                _(
                    "Used together by the “New Tiles & Cluster Growth” color "
                    "strategy to show what one activity changed: newly visited "
                    "tiles, tiles that newly joined a cluster, and tiles that were "
                    "already part of a cluster before."
                ),
                [
                    TileStyleName.NEW_TILE,
                    TileStyleName.NEW_TILE_NEW_CLUSTER,
                    TileStyleName.VISITED_NEW_CLUSTER,
                    TileStyleName.OLD_CLUSTER,
                ],
            ),
        ]
        styles = get_tile_styles()

        if request.method == "POST":
            for name, style in styles.items():
                for element in ("fill", "border", "stripe"):
                    setattr(
                        style,
                        f"{element}_color",
                        _combine_color(
                            request.form[f"{name}_{element}_color"],
                            int(request.form[f"{name}_{element}_alpha"]),
                        ),
                    )
                style.border_width = max(0, int(request.form[f"{name}_border_width"]))
                style.border_stroke = BorderStroke(
                    request.form[f"{name}_border_stroke"]
                )
            config_accessor.ui().color_strategy_cmap_opacity = float(
                request.form["cmap_opacity"]
            )
            config_accessor.ui().activity_line_color = request.form[
                "activity_line_color"
            ]
            config_accessor.ui().explorer_grid_line_color = _combine_color(
                request.form["grid_line_color"],
                int(request.form["grid_line_alpha"]),
            )
            config_accessor.ui().explorer_grid_line_min_width_px = int(
                request.form["grid_line_min_width_px"]
            )
            config_accessor.save()
            flash(_("Updated tile rendering."), category="success")

        def entry(name: TileStyleName) -> dict:
            style = styles[name]
            return {
                "name": name,
                "label": labels[name],
                "style": style,
                "default_colors": {
                    element: _split_hex_into_color_alpha(
                        TILE_STYLE_DEFAULTS[name][f"{element}_color"]
                    )
                    for element in ("fill", "border", "stripe")
                },
                "defaults": TILE_STYLE_DEFAULTS[name],
                "colors": {
                    element: _split_hex_into_color_alpha(
                        getattr(style, f"{element}_color")
                    )
                    for element in ("fill", "border", "stripe")
                },
            }

        return render_template(
            "settings/tile-rendering.html.j2",
            tile_style_groups=[
                {
                    "label": group_label,
                    "description": description,
                    "entries": [entry(name) for name in names],
                }
                for group_label, description, names in groups
            ],
            border_strokes=[
                (BorderStroke.SOLID, _("Solid")),
                (BorderStroke.DASHED, _("Dashed")),
            ],
            cmap_opacity=config_accessor.ui().color_strategy_cmap_opacity,
            activity_line_color=config_accessor.ui().activity_line_color,
            grid_line_color=_split_hex_into_color_alpha(
                config_accessor.ui().explorer_grid_line_color
            ),
            grid_line_min_width_px=config_accessor.ui().explorer_grid_line_min_width_px,
            grid_line_min_width_px_options=GRID_LINE_MIN_WIDTH_PX_OPTIONS,
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

            default_equipment_id = request.form.get("default_equipment_id")
            default_equipment_id = (
                int(default_equipment_id) if default_equipment_id else None
            )
            replaced_by_id = request.form.get("replaced_by_id")
            replaced_by_id = int(replaced_by_id) if replaced_by_id else None

            kind = Kind(name=name)
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

    @blueprint.route("/manage-kinds/delete/<int:id>", methods=["POST"])
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
            "zone_boundaries": None,
        }

        heart_rate_computer = HeartRateZoneComputer(config_accessor)
        try:
            context["zone_boundaries"] = heart_rate_computer.zone_boundaries()
        except RuntimeError:
            pass
        return render_template("settings/heart-rate.html.j2", **context)

    @blueprint.route("/privacy-zones", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def privacy_zones():
        ui_config = config_accessor.ui()
        if request.method == "POST":
            ui_config.apply_privacy_zones_to_tracks = (
                request.form.get("apply_privacy_zones_to_tracks") == "on"
            )
            ui_config.apply_privacy_zones_to_heatmap = (
                request.form.get("apply_privacy_zones_to_heatmap") == "on"
            )
            config_accessor.save()
            flasher.flash_message(
                _("Updated privacy zone settings."), FlashTypes.SUCCESS
            )
            return redirect(url_for(".privacy_zones"))

        zones = DB.session.scalars(
            sqlalchemy.select(PrivacyZone).order_by(PrivacyZone.name)
        ).all()
        return render_template(
            "settings/privacy-zones.html.j2",
            zones=zones,
            zone_geojsons={zone.id: _wrap_coordinates(zone.points) for zone in zones},
            apply_privacy_zones_to_tracks=ui_config.apply_privacy_zones_to_tracks,
            apply_privacy_zones_to_heatmap=ui_config.apply_privacy_zones_to_heatmap,
        )

    @blueprint.route("/privacy-zones/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def privacy_zones_new():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            geojson_str = request.form.get("geojson", "").strip()
            if not name:
                flasher.flash_message(_("Zone name is required."), FlashTypes.DANGER)
                return redirect(url_for(".privacy_zones_new"))
            if DB.session.scalar(
                sqlalchemy.select(PrivacyZone).where(PrivacyZone.name == name)
            ):
                flasher.flash_message(
                    _("A privacy zone named '%(name)s' already exists.", name=name),
                    FlashTypes.DANGER,
                )
                return redirect(url_for(".privacy_zones_new"))

            points = _parse_zone_geojson(name, geojson_str, flasher)
            if points is None:
                return redirect(url_for(".privacy_zones_new"))

            DB.session.add(PrivacyZone(name=name, points=points))
            DB.session.commit()
            flasher.flash_message(
                _("Privacy zone '%(name)s' added.", name=name), FlashTypes.SUCCESS
            )
            return redirect(url_for(".privacy_zones"))

        return render_template("settings/privacy-zones-new.html.j2")

    @blueprint.route("/privacy-zones/edit/<int:id>", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def privacy_zones_edit(id: int):
        zone = DB.session.get_one(PrivacyZone, id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            geojson_str = request.form.get("geojson", "").strip()
            if not name:
                flasher.flash_message(_("Zone name is required."), FlashTypes.DANGER)
                return redirect(url_for(".privacy_zones_edit", id=id))
            existing = DB.session.scalar(
                sqlalchemy.select(PrivacyZone).where(PrivacyZone.name == name)
            )
            if existing is not None and existing.id != id:
                flasher.flash_message(
                    _("A privacy zone named '%(name)s' already exists.", name=name),
                    FlashTypes.DANGER,
                )
                return redirect(url_for(".privacy_zones_edit", id=id))

            points = _parse_zone_geojson(name, geojson_str, flasher)
            if points is None:
                return redirect(url_for(".privacy_zones_edit", id=id))

            zone.name = name
            zone.points = points
            DB.session.commit()
            flasher.flash_message(
                _("Privacy zone '%(name)s' updated.", name=name), FlashTypes.SUCCESS
            )
            return redirect(url_for(".privacy_zones"))

        return render_template(
            "settings/privacy-zones-edit.html.j2",
            zone=zone,
            zone_geojson=_wrap_coordinates(zone.points),
        )

    @blueprint.route("/privacy-zones/delete/<int:id>", methods=["POST"])
    @needs_authentication(authenticator)
    def privacy_zones_delete(id: int):
        zone = DB.session.get_one(PrivacyZone, id)
        zone_name = zone.name
        DB.session.delete(zone)
        DB.session.commit()
        flasher.flash_message(
            _("Privacy zone '%(name)s' deleted.", name=zone_name), FlashTypes.SUCCESS
        )
        return redirect(url_for(".privacy_zones"))

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

    @blueprint.route("/explorer-zoom-levels", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def explorer_zoom_levels():
        ui_config = config_accessor.ui()
        if request.method == "POST":
            selected = {
                int(value)
                for value in request.form.getlist("zoom")
                if value.isdigit() and 0 <= int(value) <= 19
            }
            if selected:
                previous = set(ui_config.explorer_zoom_levels)
                ui_config.explorer_zoom_levels = sorted(selected)
                config_accessor.save()
                for zoom in sorted(previous - selected):
                    delete_tile_evolution(zoom)
                added = sorted(selected - previous)
                if added:
                    compute_tile_evolution(ui_config, added)
                flasher.flash_message(
                    _("Updated explorer zoom levels."), FlashTypes.SUCCESS
                )
            else:
                flasher.flash_message(
                    _("At least one zoom level has to be enabled."), FlashTypes.WARNING
                )
        return render_template(
            "settings/explorer-zoom-levels.html.j2",
            zoom_levels=[
                (
                    zoom,
                    EXPLORER_ZOOM_LEVEL_NAMES.get(zoom, ""),
                    zoom in ui_config.explorer_zoom_levels,
                )
                for zoom in sorted(
                    set(SELECTABLE_EXPLORER_ZOOM_LEVELS)
                    | set(ui_config.explorer_zoom_levels)
                )
            ],
        )

    @blueprint.route("/explorer-counted-activities")
    @needs_authentication(authenticator)
    def explorer_counted_activities():
        ui_config = config_accessor.ui()
        selected_kinds = set(json.loads(ui_config.explorer_filter_json).get("kind", []))
        return render_template(
            "settings/explorer-counted-activities.html.j2",
            kinds=[
                (kind.id, kind.name, kind.id in selected_kinds)
                for kind in DB.session.scalars(
                    sqlalchemy.select(Kind).order_by(Kind.name)
                ).all()
            ],
        )

    @blueprint.route("/explorer-filter", methods=["POST"])
    @needs_authentication(authenticator)
    def explorer_filter():
        ui_config = config_accessor.ui()
        selected = sorted(
            int(value) for value in request.form.getlist("kind") if value.isdigit()
        )
        primitives = {"kind": selected} if selected else {}
        if primitives != json.loads(ui_config.explorer_filter_json):
            ui_config.explorer_filter_json = json.dumps(primitives, sort_keys=True)
            config_accessor.save()
            rebuild_tile_visits_from_activity_tiles()
            for zoom in ui_config.explorer_zoom_levels:
                compute_current_state_for_zoom(zoom)
            mark_cluster_history_stale(ui_config.explorer_zoom_levels)
        flasher.flash_message(
            _("Updated the activities counting for explorer tiles."),
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".explorer_counted_activities"))

    @blueprint.route("/explorer-tiles", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def explorer_tiles():
        ui_config = config_accessor.ui()
        if request.method == "POST":
            wanted = request.form.get("count_inaccessible_in_cluster") == "on"
            if wanted != ui_config.count_inaccessible_in_cluster:
                ui_config.count_inaccessible_in_cluster = wanted
                config_accessor.save()
                # Cluster and square change immediately; the history is only
                # flagged, because replaying it is expensive.
                for zoom in ui_config.explorer_zoom_levels:
                    compute_current_state_for_zoom(zoom)
                delete_filtered_cluster_cache()
                mark_cluster_history_stale(ui_config.explorer_zoom_levels)
            flasher.flash_message(
                _("Updated explorer tile settings."), FlashTypes.SUCCESS
            )
        return render_template(
            "settings/explorer-tiles.html.j2",
            count_inaccessible_in_cluster=ui_config.count_inaccessible_in_cluster,
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
        map_tile_url = config_accessor.map().map_tile_url
        if request.method == "POST":
            map_tile_url = normalize_tile_url_template(request.form["map_tile_url"])
            error = tile_url_template_error(map_tile_url) or probe_tile_url(
                map_tile_url
            )
            if error:
                flasher.flash_message(
                    _(
                        "The map tile URL has not been saved: %(error)s",
                        error=error,
                    ),
                    FlashTypes.DANGER,
                )
            else:
                config_accessor.map().map_tile_url = map_tile_url
            config_accessor.map().map_tile_attribution = request.form[
                "map_tile_attribution"
            ]

            try:
                opacity = float(request.form["hillshade_opacity"])
            except (KeyError, ValueError):
                opacity = config_accessor.tile().hillshade_opacity
            config_accessor.tile().hillshade_opacity = min(max(opacity, 0.0), 1.0)

            blend_mode = request.form.get("hillshade_blend_mode", "multiply")
            if blend_mode not in HILLSHADE_BLEND_MODES:
                flasher.flash_message(
                    _("'%(mode)s' is not a known blend mode.", mode=blend_mode),
                    FlashTypes.WARNING,
                )
                blend_mode = "multiply"
            config_accessor.tile().hillshade_blend_mode = blend_mode

            config_accessor.save()
            if not error:
                flasher.flash_message(_("Tile settings updated."), FlashTypes.SUCCESS)
        return render_template(
            "settings/tile-source.html.j2",
            map_tile_url=map_tile_url,
            map_tile_attribution=config_accessor.map().map_tile_attribution,
            test_url=format_sample_tile_url(config_accessor.map().map_tile_url),
            hillshade_opacity=config_accessor.tile().hillshade_opacity,
            hillshade_blend_mode=config_accessor.tile().hillshade_blend_mode,
            hillshade_blend_modes=HILLSHADE_BLEND_MODES,
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


def _parse_zone_geojson(
    zone_name: str, zone_geojson_str: str, flasher: Flasher
) -> list[list[float]] | None:
    try:
        zone_geojson = json.loads(zone_geojson_str)
    except json.decoder.JSONDecodeError as e:
        flasher.flash_message(
            _(
                "Could not parse GeoJSON for %(name)s due to the following error: %(error)s",
                name=zone_name,
                error=e,
            ),
            FlashTypes.DANGER,
        )
        return None

    if zone_geojson.get("type") != "FeatureCollection":
        flasher.flash_message(
            _(
                "Pasted GeoJSON for %(name)s must be of type 'FeatureCollection'.",
                name=zone_name,
            ),
            FlashTypes.DANGER,
        )
        return None

    features = zone_geojson.get("features", [])

    if len(features) != 1:
        flasher.flash_message(
            _(
                "Pasted GeoJSON for %(name)s must contain exactly one feature. You cannot have multiple shapes for one privacy zone.",
                name=zone_name,
            ),
            FlashTypes.DANGER,
        )
        return None

    geometry = features[0]["geometry"]

    if geometry["type"] != "Polygon":
        flasher.flash_message(
            _(
                "Geometry for %(name)s is not a polygon. You need to create a polygon (or circle or rectangle).",
                name=zone_name,
            ),
            FlashTypes.DANGER,
        )
        return None

    coordinates = geometry["coordinates"]

    if len(coordinates) != 1:
        flasher.flash_message(
            _(
                "Polygon for %(name)s consists of multiple polygons. Please supply a simple one.",
                name=zone_name,
            ),
            FlashTypes.DANGER,
        )
        return None

    return coordinates[0]


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
