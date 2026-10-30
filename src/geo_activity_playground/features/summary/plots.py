import datetime

import altair as alt
import pandas as pd
from flask_babel import gettext as _

from ...webui.columns import ColumnDescription
from ...webui.plot_util import to_vega


def plot_per_year_per_kind(df: pd.DataFrame, column: ColumnDescription) -> str:
    return to_vega(
        alt.Chart(
            df,
            title=_("%(display_name)s per Year")
            % {"display_name": column.display_name},
        )
        .mark_bar()
        .encode(
            alt.X("year:O", title=_("Year")),
            alt.Y(
                f"sum({column.name})",
                title=f"{column.display_name} / {column.unit}",
            ),
            alt.Color("kind", title=_("Kind")),
            [
                alt.Tooltip("year", title=_("Year")),
                alt.Tooltip("kind", title=_("Kind")),
                alt.Tooltip(
                    f"sum({column.name})",
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .interactive()
    )


def plot_year_cumulative(df: pd.DataFrame, column: ColumnDescription) -> str:
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

    return to_vega(
        alt.Chart(
            year_cumulative,
            title=_("Cumulative %(display_name)s per Year")
            % {"display_name": column.display_name},
        )
        .mark_line()
        .encode(
            alt.X("week", title=_("Week")),
            alt.Y(column.name, title=f"{column.display_name} / {column.unit}"),
            alt.Color("iso_year:O", scale=alt.Scale(scheme="viridis"), title=_("Year")),
            [
                alt.Tooltip("week", title=_("Week")),
                alt.Tooltip("iso_year:O", title=_("Year")),
                alt.Tooltip(
                    column.name,
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .interactive()
    )


def plot_per_iso_week(df: pd.DataFrame, column: ColumnDescription) -> str:
    return to_vega(
        alt.Chart(
            df,
            title=_("%(display_name)s per Week")
            % {"display_name": column.display_name},
        )
        .mark_circle()
        .encode(
            alt.X("week:O", title=_("ISO Week")),
            alt.Y("iso_year:O", title=_("ISO Year")),
            alt.Size(
                f"sum({column.name})", title=f"{column.display_name} / {column.unit}"
            ),
            [
                alt.Tooltip("iso_year", title=_("ISO Year")),
                alt.Tooltip("week", title=_("ISO Week")),
                alt.Tooltip(
                    f"sum({column.name})",
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .interactive()
    )


def heatmap_per_day(df: pd.DataFrame, column: ColumnDescription) -> str:
    return to_vega(
        alt.Chart(
            _filter_past_year(df),
            title=_("%(display_name)s per day") % {"display_name": column.display_name},
        )
        .mark_rect()
        .encode(
            alt.X("iso_year_week:O", title=_("ISO Year and Week")),
            alt.Y(
                "iso_day:O",
                # scale=alt.Scale(
                #     domain=list(range(1, 8)),
                #     range=[
                #         "Monday",
                #         "Tuesday",
                #         "Wednesday",
                #         "Thursday",
                #         "Friday",
                #         "Saturday",
                #         "Sunday",
                #     ],
                # ),
                title=_("ISO Weekday"),
            ),
            alt.Color(
                f"sum({column.name})",
                scale=alt.Scale(scheme="viridis"),
                title=f"{column.display_name} / {column.unit}",
            ),
            [
                alt.Tooltip("iso_year_week", title=_("ISO Year and Week")),
                alt.Tooltip("iso_day", title=_("ISO Day")),
                alt.Tooltip(
                    f"sum({column.name})",
                    title=f"{column.display_name} / {column.unit}",
                    format=column.format,
                ),
            ],
        )
        .interactive()
    )


def _filter_past_year(df: pd.DataFrame) -> pd.DataFrame:
    now = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    start = now - datetime.timedelta(days=365)
    return df.loc[df["start_local"] >= start]
