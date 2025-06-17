import altair as alt
import pandas as pd
from flask import Blueprint
from flask import render_template
from flask.typing import ResponseReturnValue

from ..columns import column_distance
from ..columns import column_elevation_gain
from ..columns import ColumnDescription


def make_bubble_chart_blueprint(repository) -> Blueprint:
    blueprint = Blueprint("bubble_chart", __name__, template_folder="templates")

    @blueprint.route("/", endpoint="index")
    def bubble_chart() -> ResponseReturnValue:
        activities = repository.meta

        # Ensure 'activity_id' exists in the activities DataFrame
        if "activity_id" not in activities.columns:
            activities["activity_id"] = (
                activities.index
            )  # Use index as fallback if missing

        # Prepare the bubble chart data
        bubble_data = activities[
            [
                "start",
                "kind",
                "activity_id",
                column_distance.name,
                column_elevation_gain.name,
            ]
        ].rename(
            columns={
                "start": "date",
                "kind": "activity",
                "activity_id": "id",
            }
        )
        bubble_data["date"] = pd.to_datetime(bubble_data["date"]).dt.date
        bubble_data["activity_url"] = bubble_data["id"].apply(
            lambda x: f"/activity/{x}"
        )

        return render_template(
            "bubble_chart/index.html.j2",
            bubble_chart_distance=_make_bubble_chart(bubble_data, column_distance),
            bubble_chart_elevation_gain=_make_bubble_chart(
                bubble_data, column_elevation_gain
            ),
        )

    return blueprint


def _make_bubble_chart(bubble_data, column: ColumnDescription):
    return (
        alt.Chart(bubble_data, title=f"{column.display_name} per Day (Bubble Chart)")
        .mark_circle()
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y(
                f"{column.name}:Q",
                title=f"{column.display_name} ({column.unit})",
            ),
            size=alt.Size(
                f"{column.name}:Q",
                scale=alt.Scale(range=[10, 300]),
                title=f"{column.display_name}",
            ),
            color=alt.Color("activity:N", title="Activity"),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip(
                    f"{column.name}:Q",
                    title=f"{column.display_name} ({column.unit})",
                    format=column.format,
                ),
                alt.Tooltip("activity:N", title="Activity"),
                alt.Tooltip("activity_url:N", title="Activity Link"),
            ],
        )
        .properties(height=800, width=1200)
        .interactive()
        .to_json(format="vega")
    )
