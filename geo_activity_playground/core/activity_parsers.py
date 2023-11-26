import gzip
import pathlib

import fitdecode
import gpxpy
import pandas as pd


def read_fit_activity(path: pathlib.Path, open) -> pd.DataFrame:
    """
    {'timestamp': datetime.datetime(2023, 11, 11, 16, 29, 49, tzinfo=datetime.timezone.utc),
    'position_lat': <int>,
    'position_long': <int>,
    'gps_accuracy': 6,
    'enhanced_altitude': 517.2,
    'altitude': 517.2,
    'grade': 1.88,
    'distance': 4238.37,
    'heart_rate': 155,
    'calories': 253,
    'cadence': 76,
    'enhanced_speed': 3.972,
    'speed': 3.972,
    'temperature': -1,
    'ascent': 35,
    'descent': 11}
    """
    rows = []
    with open(path, "rb") as f:
        with fitdecode.FitReader(f) as fit:
            for frame in fit:
                if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                    fields = {field.name: field.value for field in frame.fields}
                    if (
                        "timestamp" in fields
                        and "position_lat" in fields
                        and "position_long" in fields
                    ):
                        row = {
                            "time": fields["timestamp"],
                            "latitude": fields["position_lat"] / ((2**32) / 360),
                            "longitude": fields["position_long"] / ((2**32) / 360),
                        }
                        if "heart_rate" in fields:
                            row["heartrate"] = fields["heart_rate"]
                        if "calories" in fields:
                            row["calories"] = fields["calories"]
                        if "cadence" in fields:
                            row["cadence"] = fields["cadence"]
                        if "distance" in fields:
                            row["distance"] = fields["distance"]
                        if "altitude" in fields:
                            row["altitude"] = fields["altitude"]
                        if "enhanced_altitude" in fields:
                            row["altitude"] = fields["enhanced_altitude"]
                        if "speed" in fields:
                            row["speed"] = fields["speed"]
                        if "enhanced_speed" in fields:
                            row["speed"] = fields["enhanced_speed"]
                        rows.append(row)

    return pd.DataFrame(rows)


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
