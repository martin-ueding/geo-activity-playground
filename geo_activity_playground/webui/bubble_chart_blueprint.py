import altair as alt
import pandas as pd
from flask import Blueprint
from flask import render_template


def make_bubble_chart_blueprint(repository):
    blueprint = Blueprint("bubble_chart", __name__, template_folder="templates")

    @blueprint.route("/", endpoint="index")
    def bubble_chart():
        activities = repository.meta

        # Ensure 'activity_id' exists in the activities DataFrame
        if "activity_id" not in activities.columns:
            activities["activity_id"] = (
                activities.index
            )  # Use index as fallback if missing

        # Prepare the bubble chart data
        bubble_data = activities[
            ["start", "distance_km", "kind", "activity_id", "elevation_gain"]
        ].rename(
            columns={
                "start": "date",
                "distance_km": "distance",
                "elevation_gain": "elevation_gain",
                "kind": "activity",
                "activity_id": "id",
            }
        )
        bubble_data["date"] = pd.to_datetime(bubble_data["date"]).dt.date
        bubble_data["activity_url"] = bubble_data["id"].apply(
            lambda x: f"/activity/{x}"
        )

        # Create the bubble chart
        bubble_chart_distance = (
            alt.Chart(bubble_data, title="Distance per Day (Bubble Chart)")
            .mark_circle()
            .encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("distance:Q", title="Distance (km)"),
                size=alt.Size(
                    "distance:Q", scale=alt.Scale(range=[10, 300]), title="Distance"
                ),
                color=alt.Color("activity:N", title="Activity"),
                tooltip=[
                    alt.Tooltip("date:T", title="Date"),
                    alt.Tooltip("distance:Q", title="Distance (km)", format=".1f"),
                    alt.Tooltip("activity:N", title="Activity"),
                    alt.Tooltip("activity_url:N", title="Activity Link"),
                ],
            )
            .properties(height=800, width=1200)
            .interactive()
            .to_json(format="vega")
        )

        bubble_chart_elevation_gain = (
            alt.Chart(bubble_data, title="Elevation Gain per Day (Bubble Chart)")
            .mark_circle()
            .encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("elevation_gain:Q", title="Elevation Gain (m)"),
                size=alt.Size(
                    "elevation_gain:Q",
                    scale=alt.Scale(range=[10, 300]),
                    title="Elevation Gain",
                ),
                color=alt.Color("activity:N", title="Activity"),
                tooltip=[
                    alt.Tooltip("date:T", title="Date"),
                    alt.Tooltip(
                        "elevation_gain:Q", title="Elevation Gain (m)", format=".0f"
                    ),
                    alt.Tooltip("activity:N", title="Activity"),
                    alt.Tooltip("activity_url:N", title="Activity Link"),
                ],
            )
            .properties(height=800, width=1200)
            .interactive()
            .to_json(format="vega")
        )
        return render_template(
            "bubble_chart/index.html.j2",
            bubble_chart_distance=bubble_chart_distance,
            bubble_chart_elevation_gain=bubble_chart_elevation_gain,
        )

    return blueprint
