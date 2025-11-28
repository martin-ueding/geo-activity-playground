import json
import urllib.parse

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
import sqlalchemy

from ...core.datamodel import DB
from ...core.datamodel import StoredSearchQuery
from ...core.meta_search import apply_search_filter
from ...core.meta_search import get_stored_queries
from ...core.meta_search import parse_search_params
from ...core.meta_search import primitives_to_jinja
from ...core.meta_search import primitives_to_json
from ...core.meta_search import register_search_query
from ..authenticator import Authenticator
from ..authenticator import needs_authentication


def make_search_blueprint(authenticator: Authenticator) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

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
