import altair as alt
import pandas as pd

from .datamodel import PlotSpec


MARKS = {
    "point": "Point",
    "circle": "Circle",
    "area": "Area",
    "bar": "Bar",
    "rect": "Rectangle",
    "line": "Line",
}
CONTINUOUS_VARIABLES = {
    "distance_km": "Distance / km",
    "distance_km_cumsum": "Cumulative Distance / km",
    "sum(distance_km)": "Total distance / km",
    "mean(distance_km)": "Average distance / km",
    "start": "Date",
    "hours": "Elapsed time / h",
    "hours_moving": "Moving time / h",
    "calories": "Energy / kcal",
    "steps": "Steps",
    "elevation_gain": "Elevation gain / m",
    "start_elevation": "Start elevation / m",
    "end_elevation": "End elevation / m",
    "sum(elevation_gain)": "Total elevation gain / m",
    "mean(elevation_gain)": "Average elevation gain / m",
    "num_new_tiles_14": "New tiles 14",
    "num_new_tiles_14": "New tiles 17",
    "average_speed_moving_kmh": "Average moving speed / km/h",
    "average_speed_elapsed_kmh": "Average elapsed speed / km/h",
    "start_latitude": "Start latitude / °",
    "start_longitude": "Start longitude / °",
    "end_latitude": "End latitude / °",
    "end_longitude": "End longitude / °",
}
DISCRETE_VARIABLES = {
    "equipment": "Equipment",
    "kind": "Activity kind",
    "consider_for_achievements": "Consider for achievements",
    "year(start):O": "Year",
    "iso_year:O": "ISO Year",
    "yearquarter(start)": "Year, Quarter",
    "yearquartermonth(start)": "Year, Quarter, Month",
    "yearmonth(start)": "Year, Month",
    "quarter(start)": "Quarter",
    "quartermonth(start)": "Quarter, Month",
    "month(start)": "Month",
    "week:O": "ISO Week",
    "date(start)": "Day of month",
    "weekday(start)": "Day of week",
    "iso_day:O": "ISO Day",
}
GROUP_BY_VARIABLES = {
    "": "(no grouping)",
    "equipment": "Equipment",
    "kind": "Activity kind",
    "consider_for_achievements": "Consider for achievements",
    "year": "Year",
    "iso_year": "ISO Year",
    "week": "ISO Week",
}

VARIABLES_1 = {"": "", **DISCRETE_VARIABLES}
VARIABLES_2 = {"": "", **DISCRETE_VARIABLES, **CONTINUOUS_VARIABLES}


def make_parametric_plot(df: pd.DataFrame, spec: PlotSpec) -> dict[str, str]:
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
