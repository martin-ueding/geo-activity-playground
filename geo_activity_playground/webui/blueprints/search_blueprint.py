import datetime
import math
import urllib.parse

import geojson
import pandas as pd
import sqlalchemy
from flask import Blueprint, Response, redirect, render_template, request
from flask.typing import ResponseReturnValue
from matplotlib import colormaps
from matplotlib.colors import to_hex

from ...core.config import Config
from ...core.datamodel import DB, Activity, StoredSearchQuery
from ...core.meta_search import (
    apply_search_filter,
    get_stored_queries,
    parse_search_params,
    primitives_to_jinja,
    primitives_to_json,
    primitives_to_url_str,
    register_search_query,
)
from ..authenticator import Authenticator, needs_authentication


def make_search_blueprint(authenticator: Authenticator, config: Config) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")
    per_page = config.search_map_tiles_per_page
    aggregate_map_activity_cap = 100
    aggregate_map_max_lines = 100

    @blueprint.route("/")
    def index():
        primitives = parse_search_params(request.args)

        if authenticator.is_authenticated():
            register_search_query(primitives)

        activities = apply_search_filter(primitives)

        stored_queries = get_stored_queries()
        search_query_favorites = [
            (str(q), q.to_url_str()) for q in stored_queries if q.is_favorite
        ]
        search_query_last = [
            (str(q), q.to_url_str()) for q in stored_queries if not q.is_favorite
        ]

        return render_template(
            "search/index.html.j2",
            activities=reversed(list(activities.iterrows())),
            base_query_str=primitives_to_url_str(primitives),
            query=primitives_to_jinja(primitives),
            search_query_favorites=search_query_favorites,
            search_query_last=search_query_last,
        )

    @blueprint.route("/map")
    def map_view():
        primitives = parse_search_params(request.args)
        page = max(1, int(request.args.get("page", 1)))

        if authenticator.is_authenticated():
            register_search_query(primitives)

        activities = apply_search_filter(primitives)
        total = len(activities)
        total_pages = math.ceil(total / per_page) if total else 1
        page = min(page, total_pages) if total_pages else 1
        slice_start = (page - 1) * per_page
        newest_first = activities.iloc[::-1]
        page_df = newest_first.iloc[slice_start : slice_start + per_page]
        activities_page = list(page_df.iterrows())

        stored_queries = get_stored_queries()
        search_query_favorites = [
            (str(q), q.to_url_str()) for q in stored_queries if q.is_favorite
        ]
        search_query_last = [
            (str(q), q.to_url_str()) for q in stored_queries if not q.is_favorite
        ]

        base_query_str = primitives_to_url_str(primitives)
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
            base_query_str=base_query_str,
            total_elapsed_time=total_elapsed_time,
            total_distance_km=total_distance_km,
            total_elevation_gain_m=total_elevation_gain_m,
            aggregate_map_count=min(total, aggregate_map_activity_cap),
            query=primitives_to_jinja(primitives),
            search_query_favorites=search_query_favorites,
            search_query_last=search_query_last,
        )

    @blueprint.route("/map/aggregate.geojson")
    def map_aggregate_geojson() -> ResponseReturnValue:
        primitives = parse_search_params(request.args)
        activities = apply_search_filter(primitives).iloc[::-1]
        activity_ids = activities["id"].head(aggregate_map_activity_cap).tolist()
        features = []
        cmap = colormaps["Dark2"]
        line_count = 0
        for i, activity in enumerate(
            DB.session.scalars(
                sqlalchemy.select(Activity).where(Activity.id.in_(activity_ids))
            ).all()
        ):
            time_series = activity.time_series
            if "latitude" not in time_series or "longitude" not in time_series:
                continue
            grouped = (
                time_series.groupby("segment_id")
                if "segment_id" in time_series.columns
                else [(0, time_series)]
            )
            for _, group in grouped:
                if line_count >= aggregate_map_max_lines:
                    break
                coordinates = [
                    [lon, lat]
                    for lat, lon in zip(group["latitude"], group["longitude"])
                    if not pd.isna(lat) and not pd.isna(lon)
                ]
                if len(coordinates) >= 2:
                    features.append(
                        geojson.Feature(
                            geometry=geojson.LineString(coordinates=coordinates),
                            properties={
                                "activity_id": activity.id,
                                "activity_name": activity.name,
                                "color": to_hex(cmap(i % 8)),
                            },
                        )
                    )
                    line_count += 1
            if line_count >= aggregate_map_max_lines:
                break
        return Response(
            geojson.dumps(geojson.FeatureCollection(features=features)),
            mimetype="application/json",
        )

    @blueprint.route("/save-search-query")
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

    @blueprint.route("/delete-search-query")
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

        return redirect(urllib.parse.unquote_plus(request.args["redirect"]))

    return blueprint
