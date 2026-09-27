import numpy as np
import pandas as pd
import pytest

from geo_activity_playground.features.similar_routes.comparison import (
    resample_track,
    track_distance_quantiles,
    tracks_overlap,
)


def test_interleaved_points_have_zero_distance(road) -> None:
    a = resample_track(road(0, 2000, 40))
    b = resample_track(road(10, 2000, 40))

    assert track_distance_quantiles(b, a)["p100"] < 0.5
    assert track_distance_quantiles(a, b)["p95"] < 0.5


def test_partial_track_is_close_only_in_one_direction(road) -> None:
    full = resample_track(road(0, 2000, 5))
    partial = resample_track(road(0, 1000, 5))

    assert track_distance_quantiles(partial, full)["p100"] < 0.5
    assert track_distance_quantiles(full, partial)["p100"] == pytest.approx(
        1000, rel=0.01
    )


def test_parallel_offset_is_measured_in_meters(road) -> None:
    a = resample_track(road(0, 2000, 5))
    b = resample_track(road(0, 2000, 5, north_m=50))

    quantiles = track_distance_quantiles(a, b)

    assert quantiles["p50"] == pytest.approx(50, rel=0.01)
    assert quantiles["mean"] == pytest.approx(50, rel=0.01)


def test_resampling_ignores_recording_density(road) -> None:
    sparse = road(0, 2000, 100)
    dense = road(0, 1000, 1)

    track = resample_track(pd.concat([dense, sparse.iloc[11:]]))
    spacing = np.diff(track.points[:, 0]) * track.meters_per_unit[1:]

    assert spacing[:-1] == pytest.approx(20, rel=0.01)


def test_recording_gaps_are_not_bridged(road) -> None:
    first = road(0, 500, 5)
    second = road(1500, 2000, 5).assign(segment_id=1)
    gapped = resample_track(pd.concat([first, second]))
    middle = resample_track(road(900, 1100, 5))

    assert track_distance_quantiles(middle, gapped)["p50"] > 400


def test_distant_tracks_do_not_overlap(road) -> None:
    a = resample_track(road(0, 2000, 5))
    b = resample_track(road(0, 2000, 5, north_m=5000))
    c = resample_track(road(0, 2000, 5, north_m=150))

    assert not tracks_overlap(a, b)
    assert tracks_overlap(a, c)


def test_track_without_coordinates_is_empty(road) -> None:
    track = resample_track(
        pd.DataFrame({"latitude": [np.nan], "longitude": [np.nan], "segment_id": [0]})
    )

    assert track.is_empty
    assert not tracks_overlap(track, resample_track(road(0, 100, 5)))
