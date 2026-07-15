import datetime
import math

import pandas as pd

from .config import ConfigAccessor


class HeartRateZoneComputer:
    def __init__(
        self,
        config_accessor: ConfigAccessor,
    ) -> None:
        self._config_accessor = config_accessor

    def compute_zones(self, frequencies: pd.Series, year: int) -> pd.Series:
        config = self._config_accessor.heart_rate()
        maximum = self._get_maximum(year)
        zones: pd.Series = (frequencies - config.heart_rate_resting) * 10 // (
            maximum - config.heart_rate_resting
        ) - 4
        zones.loc[zones < 0] = 0
        zones.loc[zones > 5] = 5
        return zones

    def zone_boundaries(self) -> list[tuple[int, int]]:
        config = self._config_accessor.heart_rate()
        maximum = self._get_maximum(datetime.date.today().year)
        result = []
        for zone in [1, 2, 3, 4, 5]:
            lower = math.ceil(
                (zone + 4) / 10 * (maximum - config.heart_rate_resting)
                + config.heart_rate_resting
            )
            upper = math.floor(
                (zone + 5) / 10 * (maximum - config.heart_rate_resting)
                + config.heart_rate_resting
            )
            result.append((lower, upper))
        return result

    def _get_maximum(self, year: int) -> int:
        config = self._config_accessor.heart_rate()
        if config.heart_rate_maximum:
            return config.heart_rate_maximum
        elif config.birth_year:
            return 220 - year + config.birth_year
        else:
            raise RuntimeError(
                "Cannot compute heart rate maximum from the given configuration items."
            )
