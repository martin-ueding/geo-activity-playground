import numpy as np
import pandas as pd

from geo_activity_playground.features.places.discovery import cluster_stays

LAT = 51.5
LON = 7.0
METERS_PER_DEGREE = 111_320.0


def _stays(activity_ids: list[int], east_m: float) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    jitter_m = rng.uniform(-15, 15, size=(len(activity_ids), 2))
    return pd.DataFrame(
        {
            "activity_id": activity_ids,
            "latitude": LAT + jitter_m[:, 0] / METERS_PER_DEGREE,
            "longitude": LON
            + (east_m + jitter_m[:, 1]) / (METERS_PER_DEGREE * np.cos(np.radians(LAT))),
        }
    )


def test_recurring_location_is_proposed() -> None:
    proposals = cluster_stays(_stays([1, 1, 2, 3, 4], east_m=0.0))

    assert len(proposals) == 1
    assert proposals[0].num_stays == 5
    assert proposals[0].num_activities == 4
    assert abs(proposals[0].latitude - LAT) < 1e-3
    assert abs(proposals[0].longitude - LON) < 1e-3


def test_location_from_too_few_activities_is_not_proposed() -> None:
    assert cluster_stays(_stays([1, 1, 2, 2], east_m=0.0)) == []


def test_separate_locations_are_separate_proposals() -> None:
    stays = pd.concat(
        [_stays([1, 2, 3], east_m=0.0), _stays([4, 5, 6, 7], east_m=500.0)],
        ignore_index=True,
    )

    proposals = cluster_stays(stays)

    assert [proposal.num_activities for proposal in proposals] == [4, 3]


def test_identical_positions_without_neighbors_are_proposed() -> None:
    stays = pd.DataFrame({"activity_id": [1, 2, 3], "latitude": LAT, "longitude": LON})

    assert len(cluster_stays(stays)) == 1


def test_no_stays() -> None:
    assert (
        cluster_stays(pd.DataFrame(columns=["activity_id", "latitude", "longitude"]))
        == []
    )
