import collections
import datetime
from typing import Any

import altair as alt
import pandas as pd
import sqlalchemy
from flask import Blueprint, render_template, request
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from sqlalchemy.orm import aliased

from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Activity, count_activities, get_activity_by_id
from ...webui.plot_util import make_kind_scale, to_vega
from .clustering import RouteCluster, cluster_routes, find_cluster, load_neighbors
from .model import QUANTILES, RouteDistance

DIRECTIONS = ["min", "max", "forward", "backward"]
MAX_RESULTS = 100
DEFAULT_MAX_DISTANCE_M = 200.0
DEFAULT_CLUSTER_QUANTILE = "p95"
DEFAULT_CLUSTER_MAX_DISTANCE_M = 100.0


def make_similar_routes_blueprint(config_accessor: ConfigAccessor) -> Blueprint:
    blueprint = Blueprint("similar_routes", __name__, template_folder="templates")

    @blueprint.route("/activity/<int:id>")
    def activity(id: int) -> ResponseReturnValue:
        quantile, max_distance_m = _distance_args("p50", DEFAULT_MAX_DISTANCE_M)
        direction = request.args.get("direction", "min")
        if direction not in DIRECTIONS:
            direction = "min"

        num_compared = DB.session.scalar(
            sqlalchemy.select(sqlalchemy.func.count()).where(
                RouteDistance.activity_id == id
            )
        )

        return render_template(
            "similar_routes/activity.html.j2",
            activity=get_activity_by_id(id),
            similar=find_similar_routes(id, quantile, direction, max_distance_m),
            quantile=quantile,
            quantiles=QUANTILES,
            direction=direction,
            directions={
                "min": _("Either lies on the other"),
                "max": _("Both lie on each other"),
                "forward": _("This lies on the other"),
                "backward": _("The other lies on this"),
            },
            max_distance_m=max_distance_m,
            num_compared=num_compared,
            num_others=count_activities() - 1,
        )

    @blueprint.route("/clusters")
    def clusters() -> ResponseReturnValue:
        quantile, max_distance_m = _distance_args(
            DEFAULT_CLUSTER_QUANTILE, DEFAULT_CLUSTER_MAX_DISTANCE_M
        )
        clusters = cluster_routes(load_neighbors(quantile, max_distance_m))
        activities = _load_activities(
            [id for cluster in clusters for id in cluster.member_ids]
        )
        return render_template(
            "similar_routes/clusters.html.j2",
            clusters=[_summarize_cluster(cluster, activities) for cluster in clusters],
            quantile=quantile,
            quantiles=QUANTILES,
            max_distance_m=max_distance_m,
        )

    @blueprint.route("/cluster/<int:id>")
    def cluster(id: int) -> ResponseReturnValue:
        quantile, max_distance_m = _distance_args(
            DEFAULT_CLUSTER_QUANTILE, DEFAULT_CLUSTER_MAX_DISTANCE_M
        )
        cluster = find_cluster(
            cluster_routes(load_neighbors(quantile, max_distance_m)), id
        )
        context: dict[str, Any] = {
            "activity": get_activity_by_id(id),
            "cluster": cluster,
            "quantile": quantile,
            "quantiles": QUANTILES,
            "max_distance_m": max_distance_m,
        }
        if cluster is not None:
            activities = _load_activities(cluster.member_ids)
            rows = _cluster_rows(cluster, activities)
            context |= {
                "center": activities[cluster.center_id],
                "names": {row["activity_id"]: row["name"] for row in rows},
                "table": rows,
                "plots": _cluster_plots(pd.DataFrame(rows), config_accessor),
            }
        return render_template("similar_routes/cluster.html.j2", **context)

    return blueprint


def _distance_args(
    default_quantile: str, default_max_distance_m: float
) -> tuple[str, float]:
    quantile = request.args.get("quantile", default_quantile)
    if quantile not in QUANTILES:
        quantile = default_quantile
    max_distance_m = request.args.get(
        "max_distance_m", default_max_distance_m, type=float
    )
    return quantile, max_distance_m


def _load_activities(ids: list[int]) -> dict[int, Activity]:
    return {
        activity.id: activity
        for activity in DB.session.scalars(
            sqlalchemy.select(Activity).where(Activity.id.in_(ids))
        )
    }


def _summarize_cluster(cluster: RouteCluster, activities: dict[int, Activity]) -> dict:
    members = [activities[id] for id in cluster.member_ids]
    starts = [activity.start for activity in members if activity.start is not None]
    names = collections.Counter(activity.name for activity in members if activity.name)
    return {
        "center": activities[cluster.center_id],
        "name": names.most_common(1)[0][0] if names else "",
        "size": len(members),
        "first": min(starts, default=None),
        "last": max(starts, default=None),
    }


def _cluster_rows(cluster: RouteCluster, activities: dict[int, Activity]) -> list[dict]:
    rows = []
    for id, distance_to_center_m in cluster.distances_to_center_m.items():
        activity = activities[id]
        rows.append(
            {
                "activity_id": id,
                "name": activity.name,
                "start": activity.start,
                "distance_to_center_m": distance_to_center_m,
                "distance_km": activity.distance_km,
                "elapsed_time": activity.elapsed_time,
                "moving_time": activity.moving_time,
                "moving_time_min": (
                    activity.moving_time.total_seconds() / 60
                    if activity.moving_time is not None
                    else None
                ),
                "average_speed_kmh": activity.average_speed_moving_kmh,
                "kind": activity.kind.name if activity.kind is not None else "",
                "equipment": (
                    activity.equipment.name if activity.equipment is not None else ""
                ),
            }
        )
    return sorted(
        rows, key=lambda row: row["start"] or datetime.datetime.min, reverse=True
    )


def _cluster_plots(df: pd.DataFrame, config_accessor: ConfigAccessor) -> dict[str, str]:
    kind_scale = make_kind_scale(df, config_accessor.ui())
    base = alt.Chart(df).mark_point(filled=True, size=60)
    tooltip = [
        alt.Tooltip("name", title=_("Name")),
        alt.Tooltip("start", title=_("Date"), type="temporal"),
        alt.Tooltip("average_speed_kmh", title=_("Average speed / km/h"), format=".1f"),
        alt.Tooltip("moving_time_min", title=_("Moving time / min"), format=".0f"),
    ]
    return {
        _("Average speed"): to_vega(
            base.encode(
                alt.X("start", title=_("Date")),
                alt.Y(
                    "average_speed_kmh",
                    title=_("Average speed / km/h"),
                    scale=alt.Scale(zero=False),
                ),
                alt.Color("kind", scale=kind_scale, title=_("Kind")),
                tooltip=tooltip,
            ).interactive()
        ),
        _("Moving time"): to_vega(
            base.encode(
                alt.X("start", title=_("Date")),
                alt.Y(
                    "moving_time_min",
                    title=_("Moving time / min"),
                    scale=alt.Scale(zero=False),
                ),
                alt.Color("kind", scale=kind_scale, title=_("Kind")),
                tooltip=tooltip,
            ).interactive()
        ),
    }


def find_similar_routes(
    activity_id: int, quantile: str, direction: str, max_distance_m: float
) -> list[tuple[Activity, float]]:
    forward = aliased(RouteDistance)
    backward = aliased(RouteDistance)
    match direction:
        case "forward":
            query = sqlalchemy.select(forward).where(forward.activity_id == activity_id)
            other_id = forward.reference_activity_id
            distance = getattr(forward, quantile)
        case "backward":
            query = sqlalchemy.select(backward).where(
                backward.reference_activity_id == activity_id
            )
            other_id = backward.activity_id
            distance = getattr(backward, quantile)
        case "min" | "max":
            query = (
                sqlalchemy.select(forward)
                .join(
                    backward,
                    (backward.activity_id == forward.reference_activity_id)
                    & (backward.reference_activity_id == forward.activity_id),
                )
                .where(forward.activity_id == activity_id)
            )
            other_id = forward.reference_activity_id
            combine = sqlalchemy.func.min if direction == "min" else sqlalchemy.func.max
            distance = combine(getattr(forward, quantile), getattr(backward, quantile))
        case _:
            raise ValueError(f"Unknown direction {direction!r}.")

    rows = DB.session.execute(
        query.join(Activity, Activity.id == other_id)
        .with_only_columns(Activity, distance, maintain_column_froms=True)
        .where(distance.is_not(None), distance <= max_distance_m)
        .order_by(distance)
        .limit(MAX_RESULTS)
    ).all()
    return [(activity, distance_m) for activity, distance_m in rows]
