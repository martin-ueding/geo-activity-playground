import altair as alt
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import get_config


class EquipmentController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    def render(self) -> dict:
        total_distances = (
            self._repository.meta.groupby("equipment")
            .apply(
                lambda group: pd.DataFrame(
                    {
                        "time": group["start"],
                        "total_distance_km": group["distance_km"].cumsum(),
                    }
                ),
                include_groups=False,
            )
            .reset_index()
        )

        kind_per_equipment = self._repository.meta.groupby("equipment").apply(
            lambda group: group.groupby("kind")
            .apply(lambda group2: sum(group2["distance_km"]), include_groups=False)
            .idxmax(),
            include_groups=False,
        )

        plot = (
            alt.Chart(
                total_distances,
                height=250,
                width=250,
                title="Equipment Usage over Time",
            )
            .mark_line(interpolate="step-after")
            .encode(
                alt.X("time", title="Date"),
                alt.Y("total_distance_km", title="Cumulative distance / km"),
            )
            .facet("equipment", columns=4, title="Equipment")
            .resolve_scale(y="independent")
            .resolve_axis(x="independent")
            .interactive()
            .to_json(format="vega")
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

        config = get_config()
        if "offsets" in config:
            for equipment, offset in config["offsets"].items():
                equipment_summary.loc[equipment, "total_distance_km"] += offset

        return {
            "total_distances_plot": plot,
            "equipment_summary": equipment_summary.reset_index().to_dict(
                orient="records"
            ),
        }
