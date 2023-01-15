import gzip
import pathlib

import fitdecode
import gpxpy
import pandas as pd

from geo_activity_playground.core.cache_dir import cache_dir

strava_checkout_path = pathlib.Path("~/Dokumente/Karten/Strava Export/").expanduser()


def read_activity(path: pathlib.Path) -> pd.DataFrame:
    activity_cache_dir = cache_dir / "activities"
    activity_cache_path = activity_cache_dir / (path.stem + ".json")
    if activity_cache_path.exists():
        return pd.read_json(activity_cache_path)
    else:
        suffixes = path.suffixes
        if suffixes[-1] == ".gz":
            if suffixes[-2] == ".gpx":
                df = read_gpx_activity(path, gzip.open)
            elif suffixes[-2] == ".fit":
                df = read_fit_activity(path, gzip.open)
            else:
                raise NotImplementedError(f"Unknown suffix: {path}")
        elif suffixes[-1] == ".gpx":
            df = read_gpx_activity(path, open)
        elif suffixes[-1] == ".fit":
            df = read_fit_activity(path, open)
        else:
            raise NotImplementedError(f"Unknown suffix: {path}")
        df.to_json(activity_cache_path)


def read_gpx_activity(path: pathlib.Path, open) -> pd.DataFrame:
    points = []
    with open(path) as f:
        gpx = gpxpy.parse(f)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points.append((point.time, point.latitude, point.longitude))

    return pd.DataFrame(points, columns=["Time", "Latitude", "Longitude"])


def read_fit_activity(path: pathlib.Path, open) -> pd.DataFrame:
    points = []
    with open(path) as f:
        with fitdecode.FitReader(f) as fit:
            for frame in fit:
                if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                    fields = {field.name: field.value for field in frame.fields}
                    if (
                        "timestamp" in fields
                        and "position_lat" in fields
                        and "position_long" in fields
                    ):
                        points.append(
                            (
                                fields["timestamp"],
                                fields["position_lat"] / ((2**32) / 360),
                                fields["position_long"] / ((2**32) / 360),
                            )
                        )

    return pd.DataFrame(points, columns=["Time", "Latitude", "Longitude"])
