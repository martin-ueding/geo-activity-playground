from functools import reduce

import dateutil.parser
from flask import Blueprint
from flask import flash
from flask import render_template
from flask import request
from flask import Response

from ..core.activities import ActivityRepository
from geo_activity_playground.core.meta_search import apply_search_query
from geo_activity_playground.core.meta_search import SearchQuery
from geo_activity_playground.webui.search_util import search_query_from_form
from geo_activity_playground.webui.search_util import SearchQueryHistory


def reduce_or(selections):
    return reduce(lambda a, b: a | b, selections)


def reduce_and(selections):
    return reduce(lambda a, b: a & b, selections)


def make_search_blueprint(
    repository: ActivityRepository, search_query_history: SearchQueryHistory
) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = apply_search_query(repository.meta, query)

        return render_template(
            "search/index.html.j2",
            activities=list(activities.iterrows()),
            query=query.to_jinja(),
        )

    return blueprint
