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


def reduce_or(selections):
    return reduce(lambda a, b: a | b, selections)


def reduce_and(selections):
    return reduce(lambda a, b: a & b, selections)


def make_search_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        print(request.args)

        query = search_query_from_form(request.args)

        # name_exact = bool(request.args.get("name_exact", False))
        # name_casing = bool(request.args.get("name_casing", False))
        # if name := request.args.get("name", ""):
        #     if name_casing:
        #         haystack = activities["name"]
        #         needle = name
        #     else:
        #         haystack = activities["name"].str.lower()
        #         needle = name.lower()
        #     if name_exact:
        #         selection = haystack == needle
        #     else:
        #         selection = [needle in an for an in haystack]
        #     activities = activities.loc[selection]

        activities = apply_search_query(repository.meta, query)

        return render_template(
            "search/index.html.j2",
            activities=list(activities.iterrows()),
            query=query.to_jinja(),
        )

    return blueprint
