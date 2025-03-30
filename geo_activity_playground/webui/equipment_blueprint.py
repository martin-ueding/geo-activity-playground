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
                    tooltip=[
                        alt.Tooltip("time:T", title="Date"),
                        alt.Tooltip(
                            "total_distance_km:Q",
                            title="Cumulative distance / km",
                            format=".0f",
                        ),
                    ],
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
                    tooltip=[
                        alt.Tooltip("year(start):O", title="Year"),
                        alt.Tooltip(
                            "sum(distance_km):Q", title="Distance / km", format=".0f"
                        ),
                        alt.Tooltip("kind:N", title="Kind"),
                    ],
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
                    tooltip=[
                        alt.Tooltip("kind:N", title="Kind"),
                        alt.Tooltip(
                            "sum(distance_km):Q", title="Distance / km", format=".0f"
                        ),
                    ],
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
        }

        return render_template("equipment/index.html.j2", **variables)

    return blueprint
