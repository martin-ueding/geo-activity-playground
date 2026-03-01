import math
import urllib.parse

import sqlalchemy
from flask import Blueprint, redirect, render_template, request

from ...core.config import Config
from ...core.datamodel import DB, StoredSearchQuery
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
            query=primitives_to_jinja(primitives),
            search_query_favorites=search_query_favorites,
            search_query_last=search_query_last,
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
