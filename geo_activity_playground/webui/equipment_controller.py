import functools

import altair as alt
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository


class EquipmentController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self) -> dict:
        total_distances = (
            self._repository.meta.groupby("equipment")
            .apply(
                lambda group: pd.DataFrame(
                    {
                        "time": group["start"],
                        "total_distance": group["distance"].cumsum(),
                    }
                )
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
                alt.Y("total_distance", title="Cumulative distance / km"),
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
                        "total_distance": group["distance"].sum(),
                        "first_use": group["start"].iloc[0],
                        "last_use": group["start"].iloc[-1],
                    },
                    index=[0],
                )
            )
            .reset_index()
            .sort_values("last_use", ascending=False)
            .to_dict(orient="records")
        )

        return {
            "total_distances_plot": plot,
            "equipment_summary": equipment_summary,
        }
