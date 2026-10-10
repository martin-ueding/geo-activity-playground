import datetime

import pandas as pd

from geo_activity_playground.core.datamodel import Activity, MapConfig
from geo_activity_playground.features.sharepic.render import (
    SHAREPIC_FIELDS,
    _activity_stat_items,
    _fit_zoom,
    _format_elapsed_time,
    _stat_rows,
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

    image = make_sharepic_base([time_series], MapConfig())
    assert image.size == (600, 600)


def test_fit_zoom_does_not_zoom_in_on_short_tracks() -> None:
    assert _fit_zoom(0.0, 0.0, 600, 600) == 16
    assert _fit_zoom(1e-5, 1e-5, 600, 600) == 16
    assert _fit_zoom(1e-3, 1e-4, 600, 600) == 11
    assert _fit_zoom(1.0, 1.0, 600, 600) == 1


def test_format_elapsed_time_rounds_microseconds_to_seconds() -> None:
    elapsed_time = pd.Timedelta(seconds=95, microseconds=732_123)
    assert _format_elapsed_time(elapsed_time) == "0:01:36"


def _activity() -> Activity:
    return Activity(
        name="Morning Ride",
        distance_km=42.0,
        elevation_gain=350.0,
        elapsed_time=datetime.timedelta(hours=2),
        moving_time=datetime.timedelta(hours=1, minutes=45),
        calories=900,
        steps=1234,
    )


def test_activity_stat_items_respects_suppressed_steps() -> None:
    labels = [label for _, label in _activity_stat_items(_activity(), ["steps"])]
    assert "STEPS" not in labels
    assert "ELEVATION GAIN" in labels


def test_settings_offer_every_rendered_field() -> None:
    rendered = {label for _, label in _activity_stat_items(_activity(), [])}
    offered = {str(label).upper() for label in SHAREPIC_FIELDS.values()}
    assert rendered <= offered


def test_stat_rows_are_balanced() -> None:
    items = [(str(i), str(i)) for i in range(7)]
    assert [len(row) for row in _stat_rows(items)] == [4, 3]
    assert [len(row) for row in _stat_rows(items[:5])] == [3, 2]
    assert [len(row) for row in _stat_rows(items[:4])] == [4]
