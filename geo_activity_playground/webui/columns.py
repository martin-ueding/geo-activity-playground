from typing import TypedDict


class ColumnDescription:
    name: str
    displayName: str
    unit: str
    format: str

    def __init__(self, name: str, displayName: str, unit: str, format: str):
        self.name = name
        self.displayName = displayName
        self.unit = unit
        self.format = format


column_distance = ColumnDescription(
    name="distance_km",
    displayName="Distance",
    unit="km",
    format=".1f",
)

column_elevation_gain = ColumnDescription(
    name="elevation_gain",
    displayName="Elevation Gain",
    unit="m",
    format=".0f",
)
