import geojson
import numpy as np

from .coordinates import get_distance
from .datamodel import Activity
from .datamodel import Segment


def extract_segment_from_geojson(geojson_str: str) -> list[list[float]]:
    gj = geojson.loads(geojson_str)
    coordinates = gj["features"][0]["geometry"]["coordinates"]
    return [[c[1], c[0]] for c in coordinates]


def segment_track_distance(segment: Segment, activity: Activity) -> float:
    """
    Computes asymmetric distance between a segment and a track in meters.

    It uses a one-sided Hausdorff distance. For every point in the segment, it computes the minimum distance to a point in the track. The maximum of these minimum distances is the result.
    """
    slat, slon = map(np.array, zip(*segment.coordinates))
    ts = activity.time_series
    tlat = ts["latitude"].to_numpy()
    tlon = ts["longitude"].to_numpy()
    d = get_distance(slat[:, None], slon[:, None], tlat[None, :], tlon[None, :])
    min_d = np.min(d, axis=1)
    return np.max(min_d)
