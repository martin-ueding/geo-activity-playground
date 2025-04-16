import dataclasses
from typing import Optional

import altair as alt
import pandas as pd


@dataclasses.dataclass
class ParametricPlotSpec:
    mark: str
    x: str
    y: str
    color: Optional[str]
    shape: Optional[str]
    size: Optional[str]
    row: Optional[str]
    column: Optional[str]


MARKS = {"point": "Point", "circle": "Circle", "area": "Area", "bar": "Bar"}
CONTINUOUS_VARIABLES = {
    "distance_km": "Distance / km",
    "sum(distance_km)": "Total distance / km",
    "mean(distance_km)": "Average distance / km",
    "start": "Date",
    "hours": "Elapsed time / h",
    "hours_moving": "Moving time / h",
    "start_latitude": "Start latitude / °",
    "start_longitude": "Start longitude / °",
    "end_latitude": "End latitude / °",
    "end_longitude": "End longitude / °",
    "start_elevation": "Start elevation / m",
    "end_elevation": "End elevation / m",
    "elevation_gain": "Elevation gain / m",
    "sum(elevation_gain)": "Total elevation gain / m",
    "mean(elevation_gain)": "Average elevation gain / m",
    "calories": "Energy / kcal",
    "steps": "Steps",
    "num_new_tiles_14": "New tiles 14",
    "num_new_tiles_14": "New tiles 17",
    "average_speed_moving_kmh": "Average moving speed / km/h",
    "average_speed_elapsed_kmh": "Average elapsed speed / km/h",
}
DISCRETE_VARIABLES = {
    "": "",
    "year(start)": "Year",
    "yearquarter(start)": "Year, Quarter",
    "yearquartermonth(start)": "Year, Quarter, Month",
    "yearmonth(start)": "Year, Month",
    "quarter(start)": "Quarter",
    "quartermonth(start)": "Quarter, Month",
    "month(start)": "Month",
    "date(start)": "Day of month",
    "weekday(start)": "Day of week",
    "iso_year": "ISO Year",
    "week": "ISO Week",
    "equipment": "Equipment",
    "kind": "Activity kind",
    "consider_for_achievements": "Consider for achievements",
}
ALL_VARIABLES = {**DISCRETE_VARIABLES, **CONTINUOUS_VARIABLES}


def make_parametric_plot(df: pd.DataFrame, spec: ParametricPlotSpec) -> str:
    chart = alt.Chart(df)

    match spec.mark:
        case "point":
            chart = chart.mark_point()
        case "circle":
            chart = chart.mark_circle()
        case "area":
            chart = chart.mark_area()
        case "bar":
            chart = chart.mark_bar()

    encodings = [
        alt.X(spec.x, title=ALL_VARIABLES[spec.x]),
        alt.Y(spec.y, title=ALL_VARIABLES[spec.y]),
    ]
    tooltips = [
        alt.Tooltip(spec.x, title=ALL_VARIABLES[spec.x]),
        alt.Tooltip(spec.y, title=ALL_VARIABLES[spec.y]),
    ]
    if spec.color:
        encodings.append(alt.Color(spec.color, title=ALL_VARIABLES[spec.color]))
        tooltips.append(alt.Tooltip(spec.color, title=ALL_VARIABLES[spec.color]))
    if spec.shape:
        encodings.append(alt.Shape(spec.shape, title=ALL_VARIABLES[spec.shape]))
        tooltips.append(alt.Tooltip(spec.shape, title=ALL_VARIABLES[spec.shape]))
    if spec.size:
        encodings.append(alt.Size(spec.size, title=ALL_VARIABLES[spec.size]))
        tooltips.append(alt.Tooltip(spec.size, title=ALL_VARIABLES[spec.size]))
    if spec.row:
        encodings.append(alt.Row(spec.row, title=ALL_VARIABLES[spec.row]))
        tooltips.append(alt.Tooltip(spec.row, title=ALL_VARIABLES[spec.row]))
    if spec.column:
        encodings.append(alt.Column(spec.column, title=ALL_VARIABLES[spec.column]))
        tooltips.append(alt.Tooltip(spec.column, title=ALL_VARIABLES[spec.column]))

    return chart.encode(*encodings).interactive().to_json(format="vega")
