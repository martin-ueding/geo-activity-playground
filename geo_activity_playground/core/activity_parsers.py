import gzip
import pathlib

import fitdecode
import gpxpy
import pandas as pd


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

    return pd.DataFrame(points, columns=["time", "latitude", "longitude"])


def read_gpx_activity(path: pathlib.Path, open) -> pd.DataFrame:
    points = []
    with open(path) as f:
        gpx = gpxpy.parse(f)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points.append((point.time, point.latitude, point.longitude))

    return pd.DataFrame(points, columns=["time", "latitude", "longitude"])


def read_activity(path: pathlib.Path) -> pd.DataFrame:
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
    if len(df):
        df.time = df.time.dt.tz_convert(None)
    df.name = path.stem.split(".")[0]
    return df
