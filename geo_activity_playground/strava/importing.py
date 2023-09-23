import functools
import gzip
import pathlib
from typing import Iterator

import fitdecode
import gpxpy
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.sources import TimeSeriesSource


@functools.cache
def activity_cache_dir() -> pathlib.Path:
    activity_cache_dir = pathlib.Path.cwd() / "Strava Export Cache" / "Activities"
    activity_cache_dir.mkdir(exist_ok=True, parents=True)
    return activity_cache_dir


def make_activity_cache_path(activity_path: pathlib.Path) -> pathlib.Path:
    return activity_cache_dir() / (activity_path.stem.split(".")[0] + ".parquet")


def extract_all_activities() -> None:
    activity_paths = list(
        (pathlib.Path.cwd() / "Strava Export" / "activities").glob("?????*.*")
    )
    activity_paths.sort()
    to_extract = [
        path for path in activity_paths if not make_activity_cache_path(path).exists()
    ]
    for path in tqdm(to_extract, desc="Extracting FIT/GPX files"):
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
        # Some FIT files don't have any location data, they might be just weight lifting. We'll skip them.
        if len(df) == 0:
            continue
        df.time = df.time.dt.tz_convert(None)
        cache_path = make_activity_cache_path(path)
        df.to_parquet(cache_path)
        pd.read_parquet(cache_path)


def read_gpx_activity(path: pathlib.Path, open) -> pd.DataFrame:
    points = []
    with open(path) as f:
        gpx = gpxpy.parse(f)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points.append((point.time, point.latitude, point.longitude))

    return pd.DataFrame(points, columns=["time", "latitude", "longitude"])


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


class StravaExportTimeSeriesSource(TimeSeriesSource):
    def __init__(self) -> None:
        extract_all_activities()

    def iter_activities(self) -> Iterator[pd.DataFrame]:
        for path in sorted(activity_cache_dir().glob("*.parquet")):
            df = pd.read_parquet(path)
            yield df

    def __str__(self) -> str:
        return "Strava Export"
