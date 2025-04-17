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
    opacity: Optional[str]
    column: Optional[str]
    facet: Optional[str]


MARKS = {
    "point": "Point",
    "circle": "Circle",
    "area": "Area",
    "bar": "Bar",
    "rect": "Rectangle",
}
CONTINUOUS_VARIABLES = {
    "distance_km": "Distance / km",
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
    "equipment:N": "Equipment",
    "kind:N": "Activity kind",
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
}

VARIABLES_1 = {"": "", **DISCRETE_VARIABLES}
VARIABLES_2 = {"": "", **DISCRETE_VARIABLES, **CONTINUOUS_VARIABLES}


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
        case "rect":
            chart = chart.mark_rect()
        case _:
            raise ValueError()

    encodings = [
        alt.X(spec.x, title=VARIABLES_2[spec.x]),
        alt.Y(spec.y, title=VARIABLES_2[spec.y]),
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
        encodings.append(alt.Size(spec.opacity, title=VARIABLES_2[spec.opacity]))
        tooltips.append(alt.Opacity(spec.opacity, title=VARIABLES_2[spec.opacity]))
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

    return chart.encode(*encodings, tooltips).interactive().to_json(format="vega")
