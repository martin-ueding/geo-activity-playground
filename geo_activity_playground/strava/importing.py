import gzip
import pathlib

import fitdecode
import gpxpy
import pandas as pd


def read_all_activities() -> pd.DataFrame:
    print("Loading activities …")
    activity_paths = list(
        (pathlib.Path.cwd() / "Strava Export" / "activities").glob("?????*.*")
    )
    activity_paths.sort()
    shards = [read_activity(activity_path) for activity_path in activity_paths]
    for path, shard in zip(activity_paths, shards):
        shard["Activity"] = int(path.stem.split(".")[0])
    print("Concatenating shards …")
    return pd.concat(shards)


def read_activity(path: pathlib.Path) -> pd.DataFrame:
    activity_cache_dir = pathlib.Path.cwd() / "Strava Export Cache" / "Activities"
    activity_cache_dir.mkdir(exist_ok=True, parents=True)
    activity_cache_path = activity_cache_dir / (path.stem.split(".")[0] + ".parquet")
    if activity_cache_path.exists():
        return pd.read_pickle(activity_cache_path)
    else:
        print(f"Loading activity {path} …")
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
        df.to_parquet(activity_cache_path)
        return df


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
