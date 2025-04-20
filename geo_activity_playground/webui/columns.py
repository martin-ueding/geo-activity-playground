import dataclasses


@dataclasses.dataclass
class ColumnDescription:
    name: str
    display_name: str
    unit: str
    format: str


column_distance = ColumnDescription(
    name="distance_km",
    display_name="Distance",
    unit="km",
    format=".1f",
)

column_elevation = ColumnDescription(
    name="elevation",
    display_name="Elevation",
    unit="m",
    format=".0f",
)
column_elevation_gain = ColumnDescription(
    name="elevation_gain",
    display_name="Elevation Gain",
    unit="m",
    format=".0f",
)

column_speed = ColumnDescription(
    name="speed",
    display_name="Speed",
    unit="km/h",
    format=".1f",
)
