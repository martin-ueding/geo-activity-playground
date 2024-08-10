import datetime
import math
from typing import Optional

import pandas as pd


class HeartRateZoneComputer:
    def __init__(
        self,
        birth_year: Optional[int] = None,
        minimum: int = 0,
        maximum: Optional[int] = None,
    ) -> None:
        self._birth_year = birth_year
        self._minimum = minimum
        self._maximum = maximum

    def compute_zones(self, frequencies: pd.Series, year: int) -> pd.Series:
        maximum = self._get_maximum(year)
        zones: pd.Series = (frequencies - self._minimum) * 10 // (
            maximum - self._minimum
        ) - 4
        zones.loc[zones < 0] = 0
        zones.loc[zones > 5] = 5
        return zones

    def zone_boundaries(self) -> list[tuple[int, int]]:
        maximum = self._get_maximum(datetime.date.today().year)
        result = []
        for zone in [1, 2, 3, 4, 5]:
            lower = math.ceil(
                (zone + 4) / 10 * (maximum - self._minimum) + self._minimum
            )
            upper = math.floor(
                (zone + 5) / 10 * (maximum - self._minimum) + self._minimum
            )
            result.append((lower, upper))
        return result

    def _get_maximum(self, year: int) -> int:
        if self._maximum:
            return self._maximum
        elif self._birth_year:
            return 220 - year + self._birth_year
        else:
            raise RuntimeError(
                "Cannot compute heart rate maximum from the given configuration items."
            )
