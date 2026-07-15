from types import SimpleNamespace

import numpy as np
import pandas as pd

from geo_activity_playground.core.datamodel import ActivityImportConfig
from geo_activity_playground.core.enrichment import enrichment_compute_tile_xy


def test_enrichment_compute_tile_xy_recomputes_invalid_coordinates() -> None:
    time_series = pd.DataFrame(
        {
            "latitude": [50.0, 50.001],
            "longitude": [7.0, 7.001],
            "x": [np.nan, np.nan],
            "y": [np.nan, np.nan],
        }
    )

    changed = enrichment_compute_tile_xy(
        SimpleNamespace(), time_series, ActivityImportConfig(), force=False
    )

    assert changed
    assert np.isfinite(time_series["x"]).all()
    assert np.isfinite(time_series["y"]).all()
