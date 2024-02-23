import collections
import itertools
import pathlib
import pickle

import numpy as np
import pandas as pd
from tqdm import tqdm

from .activities import ActivityRepository
from .coordinates import get_distance


similarity_path = pathlib.Path("Cache/activity_similarity.pickle")


def precompute_activity_distances(repository: ActivityRepository) -> None:
    raw_similarities: dict[tuple[int, int], float] = {}
    near_activities: dict[int, dict[int, float]] = collections.defaultdict(dict)

    if similarity_path.exists():
        with open(similarity_path, "rb") as f:
            raw_similarities, near_activities = pickle.load(f)

    missing_pairs = []
    for first in tqdm(repository.iter_activities(), desc="Finding new activity pairs"):
        for second in repository.iter_activities():
            meters_per_degree = 100_000
            threshold = 50 / meters_per_degree

            if (first.id, second.id) in raw_similarities:
                continue

            if (
                abs(first["start_latitude"] - second["start_latitude"]) > threshold
                or abs(first["start_longitude"] - second["start_longitude"]) > threshold
                or abs(first["end_latitude"] - second["end_latitude"]) > threshold
                or abs(first["end_latitude"] - second["end_latitude"]) > threshold
            ):
                raw_similarities[(first.id, second.id)] = 0
                raw_similarities[(second.id, first.id)] = 0
                continue

            if not (first.id, second.id) in raw_similarities:
                missing_pairs.append((first, second))

    for first, second in tqdm(missing_pairs, desc="Activity distances"):
        first_ts = repository.get_time_series(first.id)
        second_ts = repository.get_time_series(second.id)
        distance_1 = asymmetric_activity_overlap(first_ts, second_ts)
        distance_2 = asymmetric_activity_overlap(second_ts, first_ts)
        raw_similarities[(first.id, second.id)] = distance_1
        raw_similarities[(second.id, first.id)] = distance_2

        overlap = min(distance_1, distance_2)
        if overlap > 0.9:
            near_activities[first.id][second.id] = overlap
            near_activities[second.id][first.id] = overlap

    with open(similarity_path, "wb") as f:
        pickle.dump((raw_similarities, near_activities), f)


def asymmetric_activity_overlap(
    activity: pd.DataFrame, reference: pd.DataFrame
) -> float:
    sample = activity.iloc[np.linspace(0, len(activity) - 1, 50, dtype=np.int64)]
    min_distances = [
        _get_min_distance(latitude, longitude, reference)
        for (latitude, longitude) in zip(sample["latitude"], sample["longitude"])
    ]
    return sum(distance < 25 for distance in min_distances) / len(min_distances)


def _get_min_distance(latitude: float, longitude: float, other: pd.DataFrame) -> float:
    distances = get_distance(latitude, longitude, other["latitude"], other["longitude"])
    return np.min(distances)
