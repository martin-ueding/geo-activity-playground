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
                ),
            ],
        )
        .interactive()
    )


def plot_year_cumulative(df: pd.DataFrame, column: ColumnDescription) -> str:
    # One value per year and week, carried forward over weeks without activities.
    year_cumulative = (
        df.groupby(["week", "iso_year"])[column.name]
        .sum()
        .unstack("iso_year")
        .sort_index()
        .cumsum()
        .ffill(limit_area="inside")
        .stack()
        .rename(column.name)
        .reset_index()
    )
    years = sorted(year_cumulative["iso_year"].unique(), reverse=True)
    value_title = f"{column.display_name} / {column.unit}"

    # Selects the week closest to the mouse pointer, so one doesn't need to hit a line.
    hover = alt.selection_point(
        fields=["week"], nearest=True, on="pointerover", empty=False
    )

    base = alt.Chart(
        year_cumulative,
        title=_("Cumulative %(display_name)s per Year")
        % {"display_name": column.display_name},
    ).encode(alt.X("week", title=_("Week")))
    series = base.encode(
        alt.Y(column.name, title=value_title),
        alt.Color("iso_year:O", scale=alt.Scale(scheme="viridis"), title=_("Year")),
    )

    # Clicking a year in the legend highlights only it, clicking it again shows all
    # years. Ctrl-click (Cmd on macOS) adds or removes single years.
    highlight = alt.selection_point(
        name="highlight",
        fields=["iso_year"],
        bind="legend",
        toggle="event.ctrlKey || event.metaKey"
        " || (isValid(datum) && length(data('highlight_store')) == 1"
        " && data('highlight_store')[0].values[0] === datum.value)",
    )

    lines = (
        series.mark_line()
        .encode(opacity=alt.condition(highlight, alt.value(1), alt.value(0.15)))
        .add_params(highlight)
        .interactive()
    )
    points = series.mark_point(filled=True).encode(
        opacity=alt.condition(hover & highlight, alt.value(1), alt.value(0))
    )
    rule = (
        base.transform_pivot("iso_year", value=column.name, groupby=["week"])
        .mark_rule(color="gray")
        .encode(
            opacity=alt.condition(hover, alt.value(0.7), alt.value(0)),
            tooltip=[alt.Tooltip("week", title=_("Week"))]
            + [
                # A purely numeric title would be sorted to the front by JavaScript.
                alt.Tooltip(
                    f"{year}:Q",
                    title=f"{column.display_name} {year}",
                    format=column.format,
                )
                for year in years
            ],
        )
        .add_params(hover)
    )

    return to_vega(alt.layer(lines, points, rule))


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
