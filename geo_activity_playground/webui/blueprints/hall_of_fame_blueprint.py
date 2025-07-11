import collections
import logging

import pandas as pd
from flask import Blueprint
from flask import render_template
from flask import request

from ...core.activities import ActivityRepository
from ...core.activities import make_geojson_from_time_series
from ...core.meta_search import apply_search_query
from ..search_util import search_query_from_form
from ..search_util import SearchQueryHistory


logger = logging.getLogger(__name__)


def make_hall_of_fame_blueprint(
    repository: ActivityRepository,
    search_query_history: SearchQueryHistory,
) -> Blueprint:
    blueprint = Blueprint("hall_of_fame", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> str:
        query = search_query_from_form(request.args)
        search_query_history.register_query(query)
        activities = apply_search_query(repository.meta, query)
        df = activities

        nominations = nominate_activities(df)

        return render_template(
            "hall_of_fame/index.html.j2",
            nominations=[
                (
                    repository.get_activity_by_id(activity_id),
                    reasons,
                    make_geojson_from_time_series(
                        repository.get_time_series(activity_id)
                    ),
                )
                for activity_id, reasons in nominations.items()
            ],
            query=query.to_jinja(),
        )

    return blueprint


def nominate_activities(meta: pd.DataFrame) -> dict[int, list[str]]:
    nominations: dict[int, list[str]] = collections.defaultdict(list)

    _nominate_activities_inner(meta, "", nominations)

    for kind, group in meta.groupby("kind"):
        _nominate_activities_inner(group, f" for {kind}", nominations)
    for equipment, group in meta.groupby("equipment"):
        _nominate_activities_inner(group, f" with {equipment}", nominations)

    return nominations


def _nominate_activities_inner(
    meta: pd.DataFrame, title_suffix: str, nominations: dict[int, list[str]]
) -> None:
    ratings = [
        ("distance_km", "Greatest distance", "{:.1f} km"),
        ("elapsed_time", "Longest elapsed time", "{}"),
        ("average_speed_moving_kmh", "Highest average moving speed", "{:.1f} km/h"),
        ("average_speed_elapsed_kmh", "Highest average elapsed speed", "{:.1f} km/h"),
        ("calories", "Most calories burnt", "{:.0f}"),
        ("steps", "Most steps", "{:.0f}"),
        ("elevation_gain", "Largest elevation gain", "{:.0f} m"),
    ]

    for variable, title, format_str in ratings:
        if variable in meta.columns and not pd.isna(meta[variable]).all():
            try:
                i = meta[variable].idxmax()
            except ValueError as e:
                print(meta[variable].tolist())
                print(f"{meta[variable].dtype=}")
                logger.error(f"Trying to work with {variable=}.")
                logger.error(f"We got a ValueError: {e}")
            else:
                value = meta.loc[i, variable]
                format_applied = format_str.format(value)
                nominations[i].append(f"{title}{title_suffix}: {format_applied}")
