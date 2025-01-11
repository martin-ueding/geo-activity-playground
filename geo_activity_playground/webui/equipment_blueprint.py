import altair as alt
import pandas as pd
from flask import Blueprint
from flask import render_template

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.summary_stats import get_equipment_use_table


def make_equipment_blueprint(
    repository: ActivityRepository, config: Config
) -> Blueprint:
    blueprint = Blueprint("equipment", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        equipment_summary = get_equipment_use_table(
            repository.meta, config.equipment_offsets
        )

        equipment_variables = {}
        for equipment in repository.meta["equipment"].unique():
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
                    alt.X("kind", title="Kind"),
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
            "equipment_summary": equipment_summary,
        }

        return render_template("equipment/index.html.j2", **variables)

    return blueprint
