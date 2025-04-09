import altair as alt
import pandas as pd
from flask import Blueprint
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.summary_stats import get_equipment_use_table
from geo_activity_playground.webui.plot_util import make_kind_scale


def make_equipment_blueprint(
    repository: ActivityRepository, config: Config
) -> Blueprint:
    blueprint = Blueprint("equipment", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        equipment_summary = get_equipment_use_table(
            repository.meta, config.equipment_offsets
        )

        # Prepare data for the stacked area chart
        activities = repository.meta
        activities["week"] = activities["start"].dt.to_period("W").apply(lambda r: r.start_time)
        weekly_data = (
            activities.groupby(["week", "equipment"])
            .agg(total_distance=("distance_km", "sum"))
            .reset_index()
        )

        stacked_area_chart = (
            alt.Chart(weekly_data, height=300, width=600, title="Weekly Equipment Usage")
            .mark_area()
            .encode(
                x=alt.X("week:T", title="Week"),
                y=alt.Y("total_distance:Q", title="Total Kilometers per Week"),
                color=alt.Color("equipment:N", title="Equipment"),
                tooltip=[
                    alt.Tooltip("equipment:N", title="Equipment"),
                    alt.Tooltip("total_distance:Q", title="Total Distance"),
                ],
            )
            .interactive()
            .to_json(format="vega")  # Specify format="vega"
        )

        equipment_variables = {}
        for equipment in equipment_summary["equipment"]:
            selection = repository.meta.loc[repository.meta["equipment"] == equipment]
            total_distances = pd.DataFrame(
                {
                    "time": selection["start"],
                    "total_distance_km": selection["distance_km"].cumsum(),
                }
            )

            total_distances_plot = (
                alt.Chart(
                    total_distances,
                    height=300,
                    width=300,
                    title="Usage over Time",
                )
                .mark_line(interpolate="step-after")
                .encode(
                    alt.X("time", title="Date"),
                    alt.Y("total_distance_km", title="Cumulative distance / km"),
                )
                .interactive()
                .to_json(format="vega")
            )

            yearly_distance_plot = (
                alt.Chart(
                    selection,
                    height=300,
                    title="Yearly distance",
                )
                .mark_bar()
                .encode(
                    alt.X("year(start):O", title="Year"),
                    alt.Y("sum(distance_km)", title="Distance / km"),
                    alt.Color(
                        "kind",
                        scale=make_kind_scale(repository.meta, config),
                        title="Kind",
                    ),
                )
                .to_json(format="vega")
            )

            usages_plot = (
                alt.Chart(
                    selection,
                    height=300,
                    title="Kinds",
                )
                .mark_bar()
                .encode(
                    alt.X(
                        "kind",
                        title="Kind",
                    ),
                    alt.Y("sum(distance_km)", title="Distance / km"),
                )
                .to_json(format="vega")
            )

            equipment_variables[equipment] = {
                "total_distances_plot": total_distances_plot,
                "total_distances_plot_id": f"total_distances_plot_{hash(equipment)}",
                "yearly_distance_plot": yearly_distance_plot,
                "yearly_distance_plot_id": f"yearly_distance_plot_{hash(equipment)}",
                "usages_plot": usages_plot,
                "usages_plot_id": f"usages_plot_{hash(equipment)}",
            }

        variables = {
            "equipment_variables": equipment_variables,
            "equipment_summary": equipment_summary.to_dict(orient="records"),
            "stacked_area_chart": stacked_area_chart,
        }

        return render_template("equipment/index.html.j2", **variables)

    return blueprint
