from functools import reduce

import dateutil.parser
from flask import Blueprint
from flask import flash
from flask import render_template
from flask import request
from flask import Response

from ...core.activities import ActivityRepository


def reduce_or(selections):
    return reduce(lambda a, b: a | b, selections)


def reduce_and(selections):
    return reduce(lambda a, b: a & b, selections)


def make_search_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("search", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        kinds_avail = repository.meta["kind"].unique()
        equipments_avail = repository.meta["equipment"].unique()

        print(request.args)

        activities = repository.meta

        if equipments := request.args.getlist("equipment"):
            selection = reduce_or(
                activities["equipment"] == equipment for equipment in equipments
            )
            activities = activities.loc[selection]

        if kinds := request.args.getlist("kind"):
            selection = reduce_or(activities["kind"] == kind for kind in kinds)
            activities = activities.loc[selection]

        name_exact = bool(request.args.get("name_exact", False))
        name_casing = bool(request.args.get("name_casing", False))
        if name := request.args.get("name", ""):
            if name_casing:
                haystack = activities["name"]
                needle = name
            else:
                haystack = activities["name"].str.lower()
                needle = name.lower()
            if name_exact:
                selection = haystack == needle
            else:
                selection = [needle in an for an in haystack]
            activities = activities.loc[selection]

        begin = request.args.get("begin", "")
        end = request.args.get("end", "")

        if begin:
            try:
                begin_dt = dateutil.parser.parse(begin)
            except ValueError:
                flash(
                    f"Cannot parse date `{begin}`, please use a different format.",
                    category="danger",
                )
            else:
                selection = begin_dt <= activities["start"]
                activities = activities.loc[selection]

        if end:
            try:
                end_dt = dateutil.parser.parse(end)
            except ValueError:
                flash(
                    f"Cannot parse date `{end}`, please use a different format.",
                    category="danger",
                )
            else:
                selection = activities["start"] < end_dt
                activities = activities.loc[selection]

        activities = activities.sort_values("start", ascending=False)

        return render_template(
            "search/index.html.j2",
            activities=list(activities.iterrows()),
            equipments=request.args.getlist("equipment"),
            equipments_avail=sorted(equipments_avail),
            kinds=request.args.getlist("kind"),
            kinds_avail=sorted(kinds_avail),
            name=name,
            name_exact=name_exact,
            name_casing=name_casing,
            begin=begin,
            end=end,
        )

    return blueprint
