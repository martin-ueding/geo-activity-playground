import altair as alt
import numpy as np
import pandas as pd
from flask import Blueprint
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository


def make_eddington_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("eddington", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        activities = repository.meta.loc[
            repository.meta["consider_for_achievements"]
        ].copy()
        activities["day"] = [start.date() for start in activities["start"]]

        sum_per_day = activities.groupby("day").apply(
            lambda group: int(sum(group["distance_km"])), include_groups=False
        )
        counts = dict(zip(*np.unique(sorted(sum_per_day), return_counts=True)))
        eddington = pd.DataFrame(
            {"distance_km": d, "count": counts.get(d, 0)}
            for d in range(max(counts.keys()) + 1)
        )
        eddington["total"] = eddington["count"][::-1].cumsum()[::-1]
        x = list(range(1, max(eddington["distance_km"]) + 1))
        en = eddington.loc[eddington["total"] >= eddington["distance_km"]][
            "distance_km"
        ].iloc[-1]
        eddington["missing"] = eddington["distance_km"] - eddington["total"]

        logarithmic_plot = (
            (
                (
                    alt.Chart(
                        eddington,
                        height=500,
                        width=1000,
                        title=f"Eddington Number {en}",
                    )
                    .mark_area(interpolate="step")
                    .encode(
                        alt.X(
                            "distance_km",
                            scale=alt.Scale(domainMin=0),
                            title="Distance / km",
                        ),
                        alt.Y(
                            "total",
                            scale=alt.Scale(domainMax=en + 10),
                            title="Days exceeding distance",
                        ),
                        [
                            alt.Tooltip("distance_km", title="Distance / km"),
                            alt.Tooltip("total", title="Days exceeding distance"),
                            alt.Tooltip("missing", title="Days missing for next"),
                        ],
                    )
                )
                + (
                    alt.Chart(pd.DataFrame({"distance_km": x, "total": x}))
                    .mark_line(color="red")
                    .encode(alt.X("distance_km"), alt.Y("total"))
                )
            )
            .interactive()
            .to_json(format="vega")
        )
        return render_template(
            "eddington/index.html.j2",
            eddington_number=en,
            logarithmic_plot=logarithmic_plot,
            eddington_table=eddington.loc[
                (eddington["distance_km"] > en) & (eddington["distance_km"] <= en + 10)
            ].to_dict(orient="records"),
        )

    return blueprint
