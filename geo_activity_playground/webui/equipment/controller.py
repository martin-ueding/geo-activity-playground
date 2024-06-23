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
                lambda group: pd.DataFrame(
                    {
                        "total_distance_km": group["distance_km"].sum(),
                        "first_use": group["start"].iloc[0],
                        "last_use": group["start"].iloc[-1],
                    },
                    index=[0],
                ),
                include_groups=False,
            )
            .reset_index()
            .sort_values("last_use", ascending=False)
        )

        config = get_config()
        if "offsets" in config:
            for equipment, offset in config["offsets"].items():
                equipment_summary.loc[
                    equipment_summary["equipment"] == equipment, "total_distance_km"
                ] += offset

        return {
            "total_distances_plot": plot,
            "equipment_summary": equipment_summary.to_dict(orient="records"),
        }
