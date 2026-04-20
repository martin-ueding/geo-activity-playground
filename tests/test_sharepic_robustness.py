import pandas as pd

from geo_activity_playground.core.config import Config
from geo_activity_playground.webui.blueprints.activity_blueprint import (
    _format_elapsed_time,
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


def test_format_elapsed_time_rounds_microseconds_to_seconds() -> None:
    elapsed_time = pd.Timedelta(seconds=95, microseconds=732_123)
    assert _format_elapsed_time(elapsed_time) == "0:01:36"
