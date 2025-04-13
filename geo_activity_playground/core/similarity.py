import pathlib

import imagehash
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageDraw
from tqdm import tqdm

from .activities import ActivityRepository
from .coordinates import get_distance
from .tasks import stored_object


fingerprint_path = pathlib.Path("Cache/activity_fingerprints.pickle")
distances_path = pathlib.Path("Cache/activity_distances.pickle")


def add_distance(distances, this, other, distance) -> None:
    if this not in distances:
        distances[this] = {}
    if distance not in distances[this]:
        distances[this][distance] = set()
    distances[this][distance].add(other)


def precompute_activity_distances(repository: ActivityRepository) -> None:
    with stored_object(fingerprint_path, {}) as fingerprints, stored_object(
        distances_path, {}
    ) as distances:
        activity_ids = repository.get_activity_ids()

        activity_ids_without_fingerprint = [
            activity_id
            for activity_id in activity_ids
            if activity_id not in fingerprints
        ]
        for activity_id in tqdm(
            activity_ids_without_fingerprint, desc="Compute activity fingerprints"
        ):
            ts = repository.get_time_series(activity_id)
            ts_hash = _compute_image_hash(ts)
            fingerprints[activity_id] = ts_hash

        for this in tqdm(
            activity_ids_without_fingerprint, desc="Compute activity distances"
        ):
            for other in activity_ids:
                distance = _hamming_distance(fingerprints[this], fingerprints[other])
                add_distance(distances, this, other, distance)
                add_distance(distances, other, this, distance)


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


def _compute_image_hash(time_series) -> int:
    z = 12 + 8
    x = time_series["x"] * 2**z
    y = time_series["y"] * 2**z
    xy_pixels = np.array([x - x.min(), y - y.min()]).T
    dim = xy_pixels.max(axis=0)
    # Some activities have bogus data in them which makes them require a huge image. We just skip those outright and return a dummy hash value.
    if max(dim) > 6000:
        return 0
    im = Image.new("L", tuple(map(int, dim)))
    draw = ImageDraw.Draw(im)
    pixels = list(map(int, xy_pixels.flatten()))
    draw.line(pixels, fill=255, width=5)
    return int(str(imagehash.dhash(im)), 16)


def _hamming_distance(a: int, b: int) -> int:
    diff = a ^ b
    result = 0
    while diff:
        result += diff % 2
        diff //= 2
    return result
