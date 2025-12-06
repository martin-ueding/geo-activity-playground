import altair as alt
import pandas as pd
from flask_babel import lazy_gettext as _

from .datamodel import PlotSpec


MARKS = {
    "point": _("Point"),
    "circle": _("Circle"),
    "area": _("Area"),
    "bar": _("Bar"),
    "rect": _("Rectangle"),
    "line": _("Line"),
}
CONTINUOUS_VARIABLES = {
    "distance_km": _("Distance / km"),
    "distance_km_cumsum": _("Cumulative Distance / km"),
    "sum(distance_km)": _("Total distance / km"),
    "mean(distance_km)": _("Average distance / km"),
    "start_local": _("Date"),
    "hours": _("Elapsed time / h"),
    "hours_moving": _("Moving time / h"),
    "calories": _("Energy / kcal"),
    "steps": _("Steps"),
    "elevation_gain": _("Elevation gain / m"),
    "start_elevation": _("Start elevation / m"),
    "end_elevation": _("End elevation / m"),
    "sum(elevation_gain)": _("Total elevation gain / m"),
    "mean(elevation_gain)": _("Average elevation gain / m"),
    "num_new_tiles_14": _("New tiles 14"),
    "num_new_tiles_14": _("New tiles 17"),
    "average_speed_moving_kmh": _("Average moving speed / km/h"),
    "average_speed_elapsed_kmh": _("Average elapsed speed / km/h"),
    "start_latitude": _("Start latitude / °"),
    "start_longitude": _("Start longitude / °"),
    "end_latitude": _("End latitude / °"),
    "end_longitude": _("End longitude / °"),
}
DISCRETE_VARIABLES = {
    "equipment": _("Equipment"),
    "kind": _("Activity kind"),
    "consider_for_achievements": _("Consider for achievements"),
    "year(start_local):O": _("Year"),
    "iso_year:O": _("ISO Year"),
    "yearquarter(start_local)": _("Year, Quarter"),
    "yearquartermonth(start_local)": _("Year, Quarter, Month"),
    "yearmonth(start_local)": _("Year, Month"),
    "quarter(start_local)": _("Quarter"),
    "quartermonth(start_local)": _("Quarter, Month"),
    "month(start_local)": _("Month"),
    "week:O": _("ISO Week"),
    "date(start_local)": _("Day of month"),
    "weekday(start_local)": _("Day of week"),
    "iso_day:O": _("ISO Day"),
}
GROUP_BY_VARIABLES = {
    "": _("(no grouping)"),
    "equipment": _("Equipment"),
    "kind": _("Activity kind"),
    "consider_for_achievements": _("Consider for achievements"),
    "year": _("Year"),
    "iso_year": _("ISO Year"),
    "week": _("ISO Week"),
}

VARIABLES_1 = {"": "", **DISCRETE_VARIABLES}
VARIABLES_2 = {"": "", **DISCRETE_VARIABLES, **CONTINUOUS_VARIABLES}

RENAMES = {
    "year(start):O": "year(start_local):O",
    "yearquarter(start)": "yearquarter(start_local)",
    "yearquartermonth(start)": "yearquartermonth(start_local)",
    "yearmonth(start)": "yearmonth(start_local)",
    "quarter(start)": "quarter(start_local)",
    "quartermonth(start)": "quartermonth(start_local)",
    "month(start)": "month(start_local)",
    "date(start)": "date(start_local)",
    "weekday(start)": "weekday(start_local)",
}


def make_parametric_plot(df: pd.DataFrame, spec: PlotSpec) -> dict[str, str]:
    # Update renamed fields.
    for field in spec.FIELDS:
        setattr(spec, field, RENAMES.get(getattr(spec, field), getattr(spec, field)))

    if spec.group_by:
        grouped = df.groupby(spec.group_by)
    else:
        grouped = [("", df)]

    chart_groups = {}
    for key, group in grouped:
        chart = alt.Chart(group)

        match spec.mark:
            case "point":
                chart = chart.mark_point()
            case "circle":
                chart = chart.mark_circle()
            case "area":
                chart = chart.mark_area()
            case "bar":
                chart = chart.mark_bar()
            case "rect":
                chart = chart.mark_rect()
            case "line":
                chart = chart.mark_line()
            case _:
                raise ValueError()

        if spec.mark in ["area", "line"]:
            group_by_variables = [
                var.split(":")[0]
                for var in [
                    spec.color,
                    spec.shape,
                    spec.size,
                    spec.opacity,
                    spec.row,
                    spec.column,
                    spec.facet,
                ]
                if var
            ]
            for column in ["distance_km"]:
                group[column + "_cumsum"] = (
                    group[group_by_variables + [column]]
                    .groupby(group_by_variables)
                    .cumsum()
                )

        encodings = [
            (
                alt.X(spec.x, type="ordinal", title=VARIABLES_2[spec.x])
                if spec.mark == "rect"
                else alt.X(spec.x, title=VARIABLES_2[spec.x])
            ),
            (
                alt.Y(spec.y, type="ordinal", title=VARIABLES_2[spec.y])
                if spec.mark == "rect"
                else alt.Y(spec.y, title=VARIABLES_2[spec.y])
            ),
        ]
        tooltips = [
            alt.Tooltip(spec.x, title=VARIABLES_2[spec.x]),
            alt.Tooltip(spec.y, title=VARIABLES_2[spec.y]),
        ]

        if spec.color:
            encodings.append(alt.Color(spec.color, title=VARIABLES_2[spec.color]))
            tooltips.append(alt.Tooltip(spec.color, title=VARIABLES_2[spec.color]))
        if spec.shape:
            encodings.append(alt.Shape(spec.shape, title=VARIABLES_2[spec.shape]))
            tooltips.append(alt.Tooltip(spec.shape, title=VARIABLES_2[spec.shape]))
        if spec.size:
            encodings.append(alt.Size(spec.size, title=VARIABLES_2[spec.size]))
            tooltips.append(alt.Tooltip(spec.size, title=VARIABLES_2[spec.size]))
        if spec.opacity:
            encodings.append(alt.Opacity(spec.opacity, title=VARIABLES_2[spec.opacity]))
            tooltips.append(alt.Tooltip(spec.opacity, title=VARIABLES_2[spec.opacity]))
        if spec.row:
            encodings.append(alt.Row(spec.row, title=VARIABLES_2[spec.row]))
            tooltips.append(alt.Tooltip(spec.row, title=VARIABLES_2[spec.row]))
        if spec.column:
            encodings.append(alt.Column(spec.column, title=VARIABLES_2[spec.column]))
            tooltips.append(alt.Tooltip(spec.column, title=VARIABLES_2[spec.column]))
        if spec.facet:
            encodings.append(
                alt.Facet(spec.facet, columns=3, title=VARIABLES_2[spec.facet])
            )
            tooltips.append(alt.Tooltip(spec.facet, title=VARIABLES_2[spec.facet]))

        key = str(int(key) if isinstance(key, float) else key)
        chart_groups[key] = (
            chart.encode(*encodings, tooltips).interactive().to_json(format="vega")
        )
    return chart_groups
