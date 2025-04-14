import urllib.parse
from functools import reduce

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.meta_search import apply_search_query
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..search_util import search_query_from_form
from ..search_util import SearchQueryHistory


def reduce_or(selections):
    return reduce(lambda a, b: a | b, selections)


def reduce_and(selections):
    return reduce(lambda a, b: a & b, selections)


def make_search_blueprint(
    repository: ActivityRepository,
    search_query_history: SearchQueryHistory,
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = apply_search_query(repository.meta, query)

        return render_template(
            "search/index.html.j2",
            activities=reversed(list(activities.iterrows())),
            query=query.to_jinja(),
        )

    @blueprint.route("/save-search-query")
    @needs_authentication(authenticator)
    def save_search_query():
        query = search_query_from_form(request.args)
        primitives = query.to_primitives()
        if primitives not in config_accessor().search_queries_favorites:
            config_accessor().search_queries_favorites.append(primitives)
            config_accessor.save()
        return redirect(urllib.parse.unquote_plus(request.args["redirect"]))

    @blueprint.route("/delete-search-query")
    @needs_authentication(authenticator)
    def delete_search_query():
        query = search_query_from_form(request.args)
        primitives = query.to_primitives()
        if primitives in config_accessor().search_queries_favorites:
            config_accessor().search_queries_favorites.remove(primitives)
            config_accessor.save()
        return redirect(urllib.parse.unquote_plus(request.args["redirect"]))

    return blueprint
