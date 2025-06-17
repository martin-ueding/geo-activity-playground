import datetime

import altair as alt
import pandas as pd

from ..webui.columns import column_distance
from ..webui.columns import column_elevation_gain
from ..webui.columns import ColumnDescription


def plot_distance_per_year_cumulative(df: pd.DataFrame) -> str:
    return _plot_year_cumulative(df, column_distance)


def plot_elevation_gain_per_year_cumulative(df: pd.DataFrame) -> str:
    return _plot_year_cumulative(df, column_elevation_gain)


PLOTS = {
    "plot_per_year_cumulative": {
        "Distance": plot_distance_per_year_cumulative,
        "Elevation Gain": plot_elevation_gain_per_year_cumulative,
    }
}


def _plot_year_cumulative(df: pd.DataFrame, column: ColumnDescription) -> str:
    year_cumulative = (
        df[["iso_year", "week", column.name]]
        .groupby("iso_year")
        .apply(
            lambda group: pd.DataFrame(
                {
                    "week": group["week"],
                    column.name: group[column.name].cumsum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    return (
        alt.Chart(
            year_cumulative,
            title=f"Cumulative {column.display_name} per Year",
        )
        .mark_line()
        .encode(
            alt.X("week", title="Week"),
            alt.Y(column.name, title=f"{column.display_name} / {column.unit}"),
            alt.Color("iso_year:N", title="Year"),
            [
                alt.Tooltip("week", title="Week"),
                alt.Tooltip("iso_year:N", title="Year"),
                alt.Tooltip(
                    column.name,
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .interactive()
        .to_json(format="vega")
    )


def _filter_past_year(df: pd.DataFrame) -> pd.DataFrame:
    now = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    start = now - datetime.timedelta(days=365)
    return df.loc[df["start"] >= start]
