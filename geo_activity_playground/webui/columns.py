import dataclasses

from flask_babel import lazy_gettext as _


@dataclasses.dataclass
class ColumnDescription:
    name: str
    display_name: str
    unit: str
    format: str


column_distance = ColumnDescription(
    name="distance_km",
    display_name=_("Distance"),
    unit="km",
    format=".1f",
)
column_elevation_gain = ColumnDescription(
    name="elevation_gain",
    display_name=_("Elevation Gain"),
    unit="m",
    format=".0f",
)
column_hours = ColumnDescription(
    name="hours",
    display_name=_("Elapsed Time"),
    unit="h",
    format=".1f",
)
column_hours_moving = ColumnDescription(
    name="hours_moving",
    display_name=_("Moving Time"),
    unit="h",
    format=".1f",
)
column_calories = ColumnDescription(
    name="calories",
    display_name=_("Energy"),
    unit="kcal",
    format=".1f",
)
column_steps = ColumnDescription(
    name="steps",
    display_name=_("Steps"),
    unit="1",
    format=".1f",
)
META_COLUMNS = [
    column_distance,
    column_elevation_gain,
    column_hours,
    column_hours_moving,
    column_calories,
    column_steps,
]

column_speed = ColumnDescription(
    name="speed",
    display_name=_("Speed"),
    unit="km/h",
    format=".1f",
)

column_elevation = ColumnDescription(
    name="elevation",
    display_name=_("Elevation"),
    unit="m",
    format=".0f",
)

TIME_SERIES_COLUMNS = [column_speed, column_elevation]
