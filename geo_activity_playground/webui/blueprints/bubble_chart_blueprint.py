import altair as alt
import pandas as pd
from flask import Blueprint, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ..columns import ColumnDescription, column_distance, column_elevation_gain


def make_bubble_chart_blueprint(repository) -> Blueprint:
    blueprint = Blueprint("bubble_chart", __name__, template_folder="templates")

    @blueprint.route("/", endpoint="index")
    def bubble_chart() -> ResponseReturnValue:
        activities = repository.meta.copy()

        if "id" not in activities.columns:
            activities["id"] = activities.index

        bubble_data = activities[
            [
                "start_local",
                "kind",
                "id",
                column_distance.name,
                column_elevation_gain.name,
            ]
        ].rename(
            columns={
                "start_local": "date",
                "kind": "activity",
            }
        )
        bubble_data["date"] = pd.to_datetime(bubble_data["date"]).dt.date
        bubble_data["activity_url"] = bubble_data["id"].apply(
            lambda x: url_for("activity.show", id=x)
        )
        day_bubble_data = (
            bubble_data.groupby("date", as_index=False)
            .agg(
                {
                    column_distance.name: "sum",
                    column_elevation_gain.name: "sum",
                    "id": "count",
                }
            )
            .rename(columns={"id": "activities"})
        )
        day_bubble_data["day_url"] = day_bubble_data["date"].apply(
            lambda date: url_for(
                "activity.day", year=date.year, month=date.month, day=date.day
            )
        )

        return render_template(
            "bubble_chart/index.html.j2",
            bubble_chart_distance=_make_bubble_chart(bubble_data, column_distance),
            bubble_chart_elevation_gain=_make_bubble_chart(
                bubble_data, column_elevation_gain
            ),
            bubble_chart_day_distance=_make_day_bubble_chart(
                day_bubble_data, column_distance
            ),
            bubble_chart_day_elevation_gain=_make_day_bubble_chart(
                day_bubble_data, column_elevation_gain
            ),
        )

    return blueprint


def _make_bubble_chart(bubble_data, column: ColumnDescription):
    return (
        alt.Chart(
            bubble_data,
            title=_("%(display_name)s per Activity (Bubble Chart)")
            % {"display_name": column.display_name},
        )
        .mark_circle()
        .encode(
            x=alt.X("date:T", title=_("Date")),
            y=alt.Y(
                f"{column.name}:Q",
                title=f"{column.display_name} ({column.unit})",
            ),
            size=alt.Size(
                f"{column.name}:Q",
                scale=alt.Scale(range=[10, 300]),
                title=f"{column.display_name}",
            ),
            color=alt.Color("activity:N", title=_("Activity")),
            tooltip=[
                alt.Tooltip("date:T", title=_("Date")),
                alt.Tooltip(
                    f"{column.name}:Q",
                    title=f"{column.display_name} ({column.unit})",
                    format=column.format,
                ),
                alt.Tooltip("activity:N", title=_("Activity")),
                alt.Tooltip("activity_url:N", title=_("Activity Link")),
            ],
        )
        .properties(height=800, width=1200)
        .interactive()
        .to_json(format="vega")
    )


def _make_day_bubble_chart(day_bubble_data, column: ColumnDescription):
    return (
        alt.Chart(
            day_bubble_data,
            title=_("%(display_name)s per Day (Bubble Chart)")
            % {"display_name": column.display_name},
        )
        .mark_circle()
        .encode(
            x=alt.X("date:T", title=_("Date")),
            y=alt.Y(
                f"{column.name}:Q",
                title=f"{column.display_name} ({column.unit})",
            ),
            size=alt.Size(
                f"{column.name}:Q",
                scale=alt.Scale(range=[10, 600]),
                title=f"{column.display_name}",
            ),
            color=alt.Color("activities:Q", title=_("Activities")),
            tooltip=[
                alt.Tooltip("date:T", title=_("Date")),
                alt.Tooltip(
                    f"{column.name}:Q",
                    title=f"{column.display_name} ({column.unit})",
                    format=column.format,
                ),
                alt.Tooltip("activities:Q", title=_("Activities")),
                alt.Tooltip("day_url:N", title=_("Day Link")),
            ],
        )
        .properties(height=800, width=1200)
        .interactive()
        .to_json(format="vega")
    )
