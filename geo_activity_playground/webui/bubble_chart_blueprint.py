from flask import Blueprint, render_template
import altair as alt
import pandas as pd

def make_bubble_chart_blueprint(repository):
    blueprint = Blueprint("bubble_chart", __name__, template_folder="templates")

    @blueprint.route("/")
    def bubble_chart():
        # Prepare data for the bubble chart
        activities = repository.meta
        bubble_data = activities[["start", "distance_km", "kind"]].rename(
            columns={"start": "date", "distance_km": "distance", "kind": "activity"}
        )
        bubble_data["date"] = pd.to_datetime(bubble_data["date"]).dt.date

        bubble_chart = (
            alt.Chart(bubble_data, title="Distance per Day (Bubble Chart)")
            .mark_circle()
            .encode(
                x=alt.X("date:T", title="Date", axis=alt.Axis(labelAngle=-45, format="%b %d, %Y", tickCount=10)),
                y=alt.Y("distance:Q", title="Distance (km)"),
                size=alt.Size("distance:Q", scale=alt.Scale(range=[10, 300]), title="Distance"),
                color=alt.Color("activity:N", title="Activity"),
                tooltip=[
                    alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                    alt.Tooltip("distance:Q", title="Distance (km)"),
                    alt.Tooltip("activity:N", title="Activity"),
                ],
            )
            .interactive()
            .to_json(format="vega")
        )

        return render_template("bubble_chart/index.html.j2", bubble_chart=bubble_chart)

    return blueprint