import collections
import logging

import pandas as pd
from flask import Blueprint, render_template

from ...core.activities import make_geojson_from_time_series
from ...core.config import ConfigAccessor
from ...core.datamodel import (
    apply_privacy_zones_to_tracks_if_enabled,
    get_activity_by_id,
    get_time_series,
)
from ...core.meta_search import apply_search_filter
from ...webui.authenticator import Authenticator
from ...webui.search_context import search_context

logger = logging.getLogger(__name__)


def make_hall_of_fame_blueprint(
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
) -> Blueprint:
    blueprint = Blueprint("hall_of_fame", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> str:
        config = config_accessor.ui()
        primitives, search_vars = search_context(authenticator)

        activities = apply_search_filter(primitives)
        df = activities

        nominations = nominate_activities(df)

        return render_template(
            "hall_of_fame/index.html.j2",
            nominations=[
                (
                    get_activity_by_id(activity_id),
                    reasons,
                    make_geojson_from_time_series(
                        apply_privacy_zones_to_tracks_if_enabled(
                            get_time_series(activity_id), config
                        )
                    ),
                )
                for activity_id, reasons in nominations.items()
            ],
            **search_vars,
        )

    return blueprint


def nominate_activities(
    meta: pd.DataFrame, by_group: bool = True
) -> dict[int, list[str]]:
    """Records within `meta`, as a reason list per activity.

    With `by_group`, each kind and each equipment contributes its own records on
    top of the overall ones. That is what the hall of fame wants; callers with
    little room want just the overall records.
    """
    nominations: dict[int, list[str]] = collections.defaultdict(list)

    _nominate_activities_inner(meta, "", nominations)

    if by_group:
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
            except (KeyError, TypeError):
                print(meta[variable].tolist())
                print(f"{meta[variable].dtype=}")
                logger.error(f"Trying to work with {variable=}.")
                raise
            else:
                value = meta.loc[i, variable]
                format_applied = format_str.format(value)
                nominations[i].append(f"{title}{title_suffix}: {format_applied}")
