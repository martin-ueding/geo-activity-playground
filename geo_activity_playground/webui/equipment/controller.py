import altair as alt
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import Config


class EquipmentController:
    def __init__(self, repository: ActivityRepository, config: Config) -> None:
        self._repository = repository
        self._config = config

    def render(self) -> dict:
        kind_per_equipment = self._repository.meta.groupby("equipment").apply(
            lambda group: group.groupby("kind")
            .apply(lambda group2: sum(group2["distance_km"]), include_groups=False)
            .idxmax(),
            include_groups=False,
        )

        equipment_summary = (
            self._repository.meta.groupby("equipment")
            .apply(
                lambda group: pd.Series(
                    {
                        "total_distance_km": group["distance_km"].sum(),
                        "first_use": group["start"].iloc[0],
                        "last_use": group["start"].iloc[-1],
                    },
                ),
                include_groups=False,
            )
            .sort_values("last_use", ascending=False)
        )

        equipment_summary["primarily_used_for"] = None
        for equipment, kind in kind_per_equipment.items():
            equipment_summary.loc[equipment, "primarily_used_for"] = kind

        equipment_variables = {}
        for equipment in equipment_summary.index:
            selection = self._repository.meta.loc[
                self._repository.meta["equipment"] == equipment
            ]
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
                    alt.X("kind", title="Year"),
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

        for equipment, offset in self._config.equipment_offsets.items():
            if equipment in equipment_summary.index:
                equipment_summary.loc[equipment, "total_distance_km"] += offset

        return {
            "equipment_variables": equipment_variables,
            "equipment_summary": equipment_summary.reset_index().to_dict(
                orient="records"
            ),
        }
