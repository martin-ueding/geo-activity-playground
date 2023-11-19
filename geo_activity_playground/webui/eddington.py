import functools

import altair as alt
import numpy as np
import pandas as pd

from geo_activity_playground.core.activities import ActivityRepository


class EddingtonController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.cache
    def render(self) -> dict:
        activities = self._repository.meta.copy()
        activities["day"] = [start.date() for start in activities["start"]]

        sum_per_day = activities.groupby("day").apply(
            lambda group: int(sum(group["distance"]))
        )
        counts = dict(zip(*np.unique(sorted(sum_per_day), return_counts=True)))
        eddington = pd.DataFrame(
            {"distance": d, "count": counts.get(d, 0)}
            for d in range(max(counts.keys()) + 1)
        )
        eddington["total"] = eddington["count"][::-1].cumsum()[::-1]
        x = list(range(1, max(eddington["distance"]) + 1))
        en = eddington.loc[eddington["total"] >= eddington["distance"]][
            "distance"
        ].iloc[-1]
        eddington["missing"] = eddington["distance"] - eddington["total"]

        logarithmic_plot = (
            (
                (
                    alt.Chart(
                        eddington,
                        height=500,
                        width=1000,
                        title=f"Eddington Number {en}",
                    )
                    .mark_bar()
                    .encode(
                        alt.X(
                            "distance",
                            scale=alt.Scale(domainMin=0),
                            title="Distance / km",
                        ),
                        alt.Y(
                            "total",
                            scale=alt.Scale(type="log"),
                            title="Days exceeding distance",
                        ),
                        [
                            alt.Tooltip("distance", title="Distance / km"),
                            alt.Tooltip("total", title="Days exceeding distance"),
                            alt.Tooltip("missing", title="Days missing for next"),
                        ],
                    )
                )
                + (
                    alt.Chart(pd.DataFrame({"distance": x, "total": x}))
                    .mark_line(color="red")
                    .encode(alt.X("distance"), alt.Y("total"))
                )
            )
            .interactive(bind_y=False)
            .to_json(format="vega")
        )

        return {"eddington_number": en, "logarithmic_plot": logarithmic_plot}
