import dataclasses
from typing import Optional

import pandas as pd


class Activity:
    track_points: Optional[pd.DataFrame] = None
    heart_rate: Optional[pd.DataFrame] = None
