import datetime
import math
import urllib.parse

import geojson
import sqlalchemy
from flask import Blueprint, Response, redirect, render_template, request
from flask.typing import ResponseReturnValue
from matplotlib import colormaps
from matplotlib.colors import to_hex

from ...core.activities import make_track_feature
from ...core.config import ConfigAccessor
from ...core.datamodel import (
    DB,
    Activity,
    StoredSearchQuery,
    apply_privacy_zones_to_tracks_if_enabled,
)
from ...core.meta_search import (
    apply_search_filter,
    parse_search_params,
    primitives_to_json,
    register_search_query,
)
from ...features.heatmap.cache import delete_heatmap_cache_for_query
from ..authenticator import Authenticator, needs_authentication
from ..search_context import search_context


def make_search_blueprint(
    authenticator: Authenticator, config_accessor: ConfigAccessor
) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")
    aggregate_map_activity_cap = 100

    @blueprint.route("/")
    def index():
        primitives, search_vars = search_context(authenticator)

        activities = apply_search_filter(primitives)
        total = len(activities)
        elapsed_seconds = (
            activities["elapsed_time"].dt.total_seconds().fillna(0).sum()
            if total
            else 0
        )
        total_elapsed_time = datetime.timedelta(seconds=float(elapsed_seconds))
        total_distance_km = (
            float(activities["distance_km"].fillna(0).sum()) if total else 0.0
        )
        total_elevation_gain_m = (
            float(activities["elevation_gain"].fillna(0).sum()) if total else 0.0
        )

        return render_template(
            "search/index.html.j2",
            activities=reversed(list(activities.iterrows())),
            total=total,
            total_elapsed_time=total_elapsed_time,
            total_distance_km=total_distance_km,
            total_elevation_gain_m=total_elevation_gain_m,
            **search_vars,
        )

    @blueprint.route("/map")
    def map_view():
        primitives, search_vars = search_context(authenticator)
        per_page = config_accessor.ui().search_map_tiles_per_page
        page = max(1, int(request.args.get("page", 1)))

        activities = apply_search_filter(primitives)
        total = len(activities)
        total_pages = math.ceil(total / per_page) if total else 1
        page = min(page, total_pages) if total_pages else 1
        slice_start = (page - 1) * per_page
        newest_first = activities.iloc[::-1]
        page_df = newest_first.iloc[slice_start : slice_start + per_page]
        activities_page = list(page_df.iterrows())

        pagination_first = (page - 1) * per_page + 1 if total else 0
        pagination_last = min(page * per_page, total)
        elapsed_seconds = (
            activities["elapsed_time"].dt.total_seconds().fillna(0).sum()
            if total
            else 0
        )
        total_elapsed_time = datetime.timedelta(seconds=float(elapsed_seconds))
        total_distance_km = (
            float(activities["distance_km"].fillna(0).sum()) if total else 0.0
        )
        total_elevation_gain_m = (
            float(activities["elevation_gain"].fillna(0).sum()) if total else 0.0
        )

        return render_template(
            "search/map.html.j2",
            activities_page=activities_page,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            pagination_first=pagination_first,
            pagination_last=pagination_last,
            total_elapsed_time=total_elapsed_time,
            total_distance_km=total_distance_km,
            total_elevation_gain_m=total_elevation_gain_m,
            aggregate_map_count=min(total, aggregate_map_activity_cap),
            **search_vars,
        )

    @blueprint.route("/map/aggregate.geojson")
    def map_aggregate_geojson() -> ResponseReturnValue:
        primitives = parse_search_params(request.args)
        activities = apply_search_filter(primitives).iloc[::-1]
        activity_ids = activities["id"].head(aggregate_map_activity_cap).tolist()
        rank = {activity_id: i for i, activity_id in enumerate(activity_ids)}
        ui_config = config_accessor.ui()
        features = []
        cmap = colormaps["Dark2"]
        for activity in sorted(
            DB.session.scalars(
                sqlalchemy.select(Activity).where(Activity.id.in_(activity_ids))
            ).all(),
            key=lambda activity: rank[activity.id],
        ):
            time_series = apply_privacy_zones_to_tracks_if_enabled(
                activity.time_series, ui_config
            )
            feature = make_track_feature(
                time_series,
                activity_id=activity.id,
                activity_name=activity.name,
                color=to_hex(cmap(rank[activity.id] % 8)),
            )
            if feature:
                features.append(feature)
        return Response(
            geojson.dumps(geojson.FeatureCollection(features=features)),
            mimetype="application/json",
        )

    @blueprint.route("/save-search-query", methods=["POST"])
    @needs_authentication(authenticator)
    def save_search_query():
        primitives = parse_search_params(request.args)
        query_json = primitives_to_json(primitives)

        # Find the stored query and mark it as favorite
        stored = DB.session.scalars(
            sqlalchemy.select(StoredSearchQuery).where(
                StoredSearchQuery.query_json == query_json
            )
        ).first()

        if stored:
            stored.is_favorite = True
            DB.session.commit()
        else:
            # Register as new favorite
            stored = register_search_query(primitives)
            if stored:
                stored.is_favorite = True
                DB.session.commit()

        return redirect(urllib.parse.unquote_plus(request.args["redirect"]))

    @blueprint.route("/delete-search-query", methods=["POST"])
    @needs_authentication(authenticator)
    def delete_search_query():
        primitives = parse_search_params(request.args)
        query_json = primitives_to_json(primitives)

        # Find the stored query and unmark it as favorite
        stored = DB.session.scalars(
            sqlalchemy.select(StoredSearchQuery).where(
                StoredSearchQuery.query_json == query_json
            )
        ).first()

        if stored:
            stored.is_favorite = False
            DB.session.commit()
            # Only favorited queries are heatmap-cacheable, so un-favoriting
            # orphans any cached tiles for this query; clean them up here.
            delete_heatmap_cache_for_query(stored.id)

        return redirect(urllib.parse.unquote_plus(request.args["redirect"]))

    return blueprint
