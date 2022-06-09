import pathlib

import gpxpy
import pandas as pd

from ..core.entities import Activity

strava_checkout_path = pathlib.Path('~/Dokumente/Karten/Strava Export/').expanduser()


def read_gpx_activity(path: pathlib.Path) -> Activity:
    result = Activity()
    
    points = []

    with open(path) as f:
        gpx = gpxpy.parse(f)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points.append((point.time, point.latitude, point.longitude))

    result.track_points = pd.DataFrame(points, columns=["Time", "Latitude", "Longitude"])
    return result