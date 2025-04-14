import datetime
import math

import pandas as pd

from .config import Config


class HeartRateZoneComputer:
    def __init__(
        self,
        config: Config,
    ) -> None:
        self._config = config

    def compute_zones(self, frequencies: pd.Series, year: int) -> pd.Series:
        maximum = self._get_maximum(year)
        zones: pd.Series = (frequencies - self._config.heart_rate_resting) * 10 // (
            maximum - self._config.heart_rate_resting
        ) - 4
        zones.loc[zones < 0] = 0
        zones.loc[zones > 5] = 5
        return zones

    def zone_boundaries(self) -> list[tuple[int, int]]:
        maximum = self._get_maximum(datetime.date.today().year)
        result = []
        for zone in [1, 2, 3, 4, 5]:
            lower = math.ceil(
                (zone + 4) / 10 * (maximum - self._config.heart_rate_resting)
                + self._config.heart_rate_resting
            )
            upper = math.floor(
                (zone + 5) / 10 * (maximum - self._config.heart_rate_resting)
                + self._config.heart_rate_resting
            )
            result.append((lower, upper))
        return result

    def _get_maximum(self, year: int) -> int:
        if self._config.heart_rate_maximum:
            return self._config.heart_rate_maximum
        elif self._config.birth_year:
            return 220 - year + self._config.birth_year
        else:
            raise RuntimeError(
                "Cannot compute heart rate maximum from the given configuration items."
            )
