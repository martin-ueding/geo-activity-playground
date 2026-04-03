import pandas as pd

from geo_activity_playground.core.config import Config
from geo_activity_playground.webui.blueprints.activity_blueprint import (
    make_sharepic_base,
)


def test_make_sharepic_base_handles_missing_tile_coordinates() -> None:
    time_series = pd.DataFrame(
        {
            "x": [float("nan"), float("nan")],
            "y": [float("nan"), float("nan")],
            "segment_id": [0, 0],
        }
    )

    image = make_sharepic_base([time_series], Config())
    assert image.size == (600, 600)
