import io
import zipfile
from typing import IO

import geojson
import gpxpy.gpx
import pandas as pd
import sqlalchemy
from tqdm import tqdm

from .datamodel import Activity
from .datamodel import DB
from .datamodel import query_activity_meta


def export_all(meta_format: str, activity_format: str) -> bytes:
    meta = query_activity_meta()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "x") as zf:
        with zf.open(f"activities.{meta_format}", mode="w") as f:
            match meta_format:
                case "csv":
                    export_meta_as_csv(meta, f)
                case "json":
                    export_meta_as_json(meta, f)
                case "ods":
                    export_meta_as_xlsx(meta, f)
                case "parquet":
                    export_meta_as_parquet(meta, f)
                case "xlsx":
                    export_meta_as_xlsx(meta, f)
                case _:
                    raise ValueError(
                        f"Format {meta_format} is not supported for metadata."
                    )
        if activity_format:
            zf.mkdir("activities")
            for activity in tqdm(
                DB.session.scalars(sqlalchemy.select(Activity)).all(),
                desc="Export activity time series",
            ):
                with zf.open(
                    f"activities/{activity.id}.{activity_format}", mode="w"
                ) as f:
                    match activity_format:
                        case "csv":
                            export_activity_as_csv(activity, f)
                        case "geojson":
                            export_activity_as_geojson(activity, f)
                        case "gpx":
                            export_activity_as_gpx(activity, f)
                        case "ods":
                            export_activity_as_xlsx(activity, f)
                        case "parquet":
                            export_activity_as_parquet(activity, f)
                        case "xlsx":
                            export_activity_as_xlsx(activity, f)
                        case _:
                            raise ValueError(
                                f"Format {activity_format} is not supported for activity time series."
                            )
    return bytes(buffer.getbuffer())


def export_meta_as_csv(meta: pd.DataFrame, target: IO[bytes]) -> None:
    meta.to_csv(target, index=False)


def export_meta_as_json(meta: pd.DataFrame, target: IO[bytes]) -> None:
    buffer = io.StringIO()
    meta.to_json(buffer, index=False)
    target.write(buffer.getvalue().encode())


def export_meta_as_parquet(meta: pd.DataFrame, target: IO[bytes]) -> None:
    meta.to_parquet(target, index=False)


def export_meta_as_xlsx(meta: pd.DataFrame, target: IO[bytes]) -> None:
    meta.to_excel(target, index=False)


def export_activity_as_csv(activity: Activity, target: IO[bytes]) -> None:
    activity.time_series.to_csv(target, index=False)


def export_activity_as_geojson(activity: Activity, target: IO[bytes]) -> None:
    ts = activity.time_series
    result = geojson.MultiLineString(
        coordinates=[
            [(lon, lat) for lat, lon in zip(group["latitude"], group["longitude"])]
            for segment_id, group in ts.groupby("segment_id")
        ]
    )
    buffer = io.StringIO()
    geojson.dump(result, buffer)
    target.write(buffer.getvalue().encode())


def export_activity_as_gpx(activity: Activity, target: IO[bytes]) -> None:
    g = gpxpy.gpx.GPX()

    gpx_track = gpxpy.gpx.GPXTrack()
    g.tracks.append(gpx_track)

    ts = activity.time_series
    for segment_id, group in ts.groupby("segment_id"):
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)

        for index, row in group.iterrows():
            gpx_segment.points.append(
                gpxpy.gpx.GPXTrackPoint(
                    row["latitude"],
                    row["longitude"],
                    elevation=row.get("elevation", None),
                    time=row.get("time", None),
                )
            )

    target.write(g.to_xml().encode())


def export_activity_as_parquet(activity: Activity, target: IO[bytes]) -> None:
    activity.time_series.to_parquet(target, index=False)


def export_activity_as_xlsx(activity: Activity, target: IO[bytes]) -> None:
    activity.time_series.to_excel(target, index=False)
