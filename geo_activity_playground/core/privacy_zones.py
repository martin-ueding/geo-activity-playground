import pandas as pd
import shapely


class PrivacyZone:
    def __init__(self, points: list[list[float]]) -> None:
        self.points = points
        self._polygon = shapely.Polygon(points)
        shapely.prepare(self._polygon)

    def filter_time_series(self, time_series: pd.DataFrame) -> pd.DataFrame:
        mask = [
            not shapely.contains_xy(self._polygon, row["longitude"], row["latitude"])
            for index, row in time_series.iterrows()
        ]
        return time_series.loc[mask]
