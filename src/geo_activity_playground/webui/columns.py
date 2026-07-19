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

column_heartrate = ColumnDescription(
    name="heartrate",
    display_name=_("Heart Rate"),
    unit="bpm",
    format=".0f",
)

column_cadence = ColumnDescription(
    name="cadence",
    display_name=_("Cadence"),
    unit="",
    format=".0f",
)

column_power = ColumnDescription(
    name="power",
    display_name=_("Power"),
    unit="W",
    format=".0f",
)

TIME_SERIES_COLUMNS = [
    column_speed,
    column_elevation,
    column_heartrate,
    column_cadence,
    column_power,
]

column_duration = ColumnDescription(
    name="duration",
    display_name=_("Duration"),
    unit="",
    format="",
)
column_direction = ColumnDescription(
    name="direction",
    display_name=_("Direction"),
    unit="",
    format="",
)
column_equipment = ColumnDescription(
    name="equipment",
    display_name=_("Equipment"),
    unit="",
    format="",
)
column_kind = ColumnDescription(
    name="kind",
    display_name=_("Kind"),
    unit="",
    format="",
)
column_average_speed = ColumnDescription(
    name="average_speed",
    display_name=_("Average Speed"),
    unit="km/h",
    format=".1f",
)
column_average_power = ColumnDescription(
    name="average_power",
    display_name=_("Average Power"),
    unit="W",
    format=".0f",
)

# Columns that the user can toggle for summary tables across the app. The
# `name` field doubles as the key persisted in Config.visible_table_columns
# and is referenced from templates as `visible[<name>]`.
TOGGLEABLE_TABLE_COLUMNS = [
    ColumnDescription(
        name="distance",
        display_name=_("Distance"),
        unit="km",
        format=".1f",
    ),
    column_duration,
    column_direction,
    column_average_speed,
    column_average_power,
    column_equipment,
    column_kind,
]
