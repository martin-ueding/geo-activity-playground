import sqlalchemy
from flask import Blueprint, render_template, request
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from sqlalchemy.orm import aliased

from ...core.datamodel import DB, Activity, count_activities, get_activity_by_id
from .model import QUANTILES, RouteDistance

DIRECTIONS = ["min", "max", "forward", "backward"]
MAX_RESULTS = 100
DEFAULT_MAX_DISTANCE_M = 200.0


def make_similar_routes_blueprint() -> Blueprint:
    blueprint = Blueprint("similar_routes", __name__, template_folder="templates")

    @blueprint.route("/activity/<int:id>")
    def activity(id: int) -> ResponseReturnValue:
        quantile = request.args.get("quantile", "p50")
        if quantile not in QUANTILES:
            quantile = "p50"
        direction = request.args.get("direction", "min")
        if direction not in DIRECTIONS:
            direction = "min"
        max_distance_m = request.args.get(
            "max_distance_m", DEFAULT_MAX_DISTANCE_M, type=float
        )

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

    return blueprint


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
