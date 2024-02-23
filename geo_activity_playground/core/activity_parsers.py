import datetime
import gzip
import logging
import pathlib
import xml

import charset_normalizer
import dateutil.parser
import fitdecode
import gpxpy
import numpy as np
import pandas as pd
import tcxreader.tcxreader
import xmltodict

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.coordinates import get_distance

logger = logging.getLogger(__name__)


class ActivityParseError(BaseException):
    pass


def read_activity(path: pathlib.Path) -> tuple[ActivityMeta, pd.DataFrame]:
    suffixes = path.suffixes
    metadata = ActivityMeta()

    if suffixes[-1] == ".gz":
        opener = gzip.open
        file_type = suffixes[-2]
    else:
        opener = open
        file_type = suffixes[-1]

    if file_type == ".gpx":
        try:
            timeseries = read_gpx_activity(path, opener)
        except gpxpy.gpx.GPXXMLSyntaxException as e:
            raise ActivityParseError(f"Syntax error while parsing GPX file") from e
        except UnicodeDecodeError as e:
            raise ActivityParseError(f"Encoding issue") from e
    elif file_type == ".fit":
        metadata, timeseries = read_fit_activity(path, opener)
    elif file_type == ".tcx":
        try:
            timeseries = read_tcx_activity(path, opener)
        except xml.etree.ElementTree.ParseError as e:
            raise ActivityParseError(f"Syntax error in TCX file") from e
    elif file_type in [".kml", ".kmz"]:
        timeseries = read_kml_activity(path, opener)
    elif file_type == ".csv":  # Simra csv export
        timeseries = read_simra_activity(path, opener)
    else:
        raise ActivityParseError(f"Unsupported file format: {file_type}")

    if len(timeseries):
        # Unify time zones to UTC.
        try:
            if timeseries["time"].dt.tz is not None:
                timeseries["time"] = timeseries["time"].dt.tz_localize(None)
            timeseries["time"] = timeseries["time"].dt.tz_localize("UTC")
        except AttributeError as e:
            print(timeseries)
            print(timeseries.dtypes)
            types = {}
            for elem in timeseries["time"]:
                t = str(type(elem))
                if t not in types:
                    types[t] = elem
            print(types)
            raise ActivityParseError(
                "It looks like the date parsing has gone wrong."
            ) from e

        # Add distance column if missing.
        if "distance_km" not in timeseries.columns:
            distances = [0] + [
                get_distance(lat_1, lon_1, lat_2, lon_2)
                for lat_1, lon_1, lat_2, lon_2 in zip(
                    timeseries["latitude"],
                    timeseries["longitude"],
                    timeseries["latitude"].iloc[1:],
                    timeseries["longitude"].iloc[1:],
                )
            ]
            timeseries["distance_km"] = pd.Series(np.cumsum(distances)) / 1000

        # Extract some meta data from the time series.
        metadata["start"] = timeseries["time"].iloc[0]
        metadata["elapsed_time"] = (
            timeseries["time"].iloc[-1] - timeseries["time"].iloc[0]
        )
        metadata["distance_km"] = timeseries["distance_km"].iloc[-1]
        if "calories" in timeseries.columns:
            metadata["calories"] = timeseries["calories"].iloc[-1]

    return metadata, timeseries


def read_fit_activity(path: pathlib.Path, open) -> tuple[ActivityMeta, pd.DataFrame]:
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
    metadata = ActivityMeta()
    rows = []
    with open(path, "rb") as f:
        with fitdecode.FitReader(f) as fit:
            for frame in fit:
                if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                    fields = {
                        field.name: field for field in frame.fields if field.value
                    }
                    values = {
                        field.name: field.value for field in frame.fields if field.value
                    }
                    if (
                        "timestamp" in values
                        and values.get("position_lat", None)
                        and values.get("position_long", None)
                    ):
                        time = values["timestamp"]
                        assert isinstance(time, datetime.datetime)
                        time = time.astimezone(datetime.timezone.utc)
                        row = {
                            "time": time,
                            "latitude": values["position_lat"] / ((2**32) / 360),
                            "longitude": values["position_long"] / ((2**32) / 360),
                        }
                        if "heart_rate" in fields:
                            row["heartrate"] = values["heart_rate"]
                        if "calories" in fields:
                            row["calories"] = values["calories"]
                        if "cadence" in fields:
                            row["cadence"] = values["cadence"]
                        if "distance" in fields:
                            row["distance"] = values["distance"]
                        if "altitude" in fields:
                            row["altitude"] = values["altitude"]
                        if "enhanced_altitude" in fields:
                            row["altitude"] = values["enhanced_altitude"]
                        if "speed" in fields:
                            factor = _fit_speed_unit_factor(fields["speed"].units)
                            row["speed"] = values["speed"] * factor
                        if "enhanced_speed" in fields:
                            factor = _fit_speed_unit_factor(
                                fields["enhanced_speed"].units
                            )
                            row["speed"] = values["enhanced_speed"] * factor
                        if "grade" in fields:
                            row["grade"] = values["grade"]
                        if "temperature" in fields:
                            row["temperature"] = values["temperature"]
                        if "gps_accuracy" in fields:
                            row["gps_accuracy"] = values["gps_accuracy"]
                        rows.append(row)

                    # Additional meta data fields as documented in https://developer.garmin.com/fit/file-types/workout/.
                    if "wkt_name" in fields:
                        metadata["name"] = values["wkt_name"]
                    if "sport" in fields:
                        metadata["kind"] = str(values["sport"])
                        if "sub_sport" in values:
                            metadata["kind"] += " " + str(values["sub_sport"])

    return metadata, pd.DataFrame(rows)


def _fit_speed_unit_factor(unit: str) -> float:
    if unit == "m/s":
        return 3.6
    elif unit == "km/h":
        return 1.0
    else:
        raise ActivityParseError(f"Unknown speed unit {unit}")


def read_gpx_activity(path: pathlib.Path, open) -> pd.DataFrame:
    points = []
    with open(path, "rb") as f:
        content = f.read()

    try:
        gpx = gpxpy.parse(content)
    except UnicodeDecodeError:
        logger.warning(f"Cannot parse the following with UTF-8: {repr(content[:1000])}")
        decoded = str(charset_normalizer.from_bytes(content).best())
        gpx = gpxpy.parse(decoded)

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if isinstance(point.time, datetime.datetime):
                    time = point.time
                else:
                    time = dateutil.parser.parse(str(point.time))
                assert isinstance(time, datetime.datetime)
                time = time.astimezone(datetime.timezone.utc)
                points.append((time, point.latitude, point.longitude, point.elevation))

    df = pd.DataFrame(points, columns=["time", "latitude", "longitude", "altitude"])
    # Some files don't have altitude information. In these cases we remove the column.
    if not df["altitude"].any():
        del df["altitude"]
    return df


def read_tcx_activity(path: pathlib.Path, opener) -> pd.DataFrame:
    """
    cadence = {NoneType} None
     distance = {float} 7.329999923706055
     elevation = {float} 2250.60009765625
     hr_value = {int} 87
     latitude = {float} 46.49582446552813
     longitude = {float} 15.50408081151545
     time = {datetime} 2020-12-26 15:14:28
     tpx_ext = {dict: 2} {'Speed': 0.7459999918937683, 'RunCadence': 58}
    """
    rows = []
    tcx_reader = tcxreader.tcxreader.TCXReader()

    with opener(path, "rb") as f:
        content = f.read().strip()

    stripped_file = pathlib.Path("Cache/temp.tcx")
    with open(stripped_file, "wb") as f:
        f.write(content)
    data = tcx_reader.read(str(stripped_file))
    stripped_file.unlink()

    for trackpoint in data.trackpoints:
        if trackpoint.latitude and trackpoint.longitude:
            time = trackpoint.time
            assert isinstance(time, datetime.datetime)
            time = time.astimezone(datetime.timezone.utc)
            row = {
                "time": time,
                "latitude": trackpoint.latitude,
                "longitude": trackpoint.longitude,
            }
            if trackpoint.elevation:
                row["altitude"] = trackpoint.elevation
            if trackpoint.hr_value:
                row["heartrate"] = trackpoint.hr_value
            if trackpoint.cadence:
                row["cadence"] = trackpoint.cadence
            if trackpoint.distance:
                row["distance"] = trackpoint.distance
            rows.append(row)
    df = pd.DataFrame(rows)
    return df


def read_kml_activity(path: pathlib.Path, opener) -> pd.DataFrame:
    with opener(path, "rb") as f:
        kml_dict = xmltodict.parse(f)
    doc = kml_dict["kml"]["Document"]
    keypoint_folder = doc["Folder"]
    placemark = keypoint_folder["Placemark"]
    track = placemark["gx:Track"]
    rows = []
    for when, where in zip(track["when"], track["gx:coord"]):
        time = dateutil.parser.parse(when).astimezone(datetime.timezone.utc)
        parts = where.split(" ")
        if len(parts) == 2:
            lon, lat = parts
            alt = None
        if len(parts) == 3:
            lon, lat, alt = parts
        row = {"time": time, "latitude": float(lat), "longitude": float(lon)}
        if alt is not None:
            row["altitude"] = float(alt)
        rows.append(row)
    return pd.DataFrame(rows)


def read_simra_activity(path: pathlib.Path, opener) -> pd.DataFrame:
    data = pd.read_csv(path, header=1)
    data["time"] = data["timeStamp"].apply(
        lambda d: datetime.datetime.fromtimestamp(d / 1000)
    )
    tz = (
        datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
    )  # get local timezone
    data["time"] = data["time"].dt.tz_localize(tz)
    data["time"] = data["time"].dt.tz_convert("UTC")
    data = data.rename(columns={"lat": "latitude", "lon": "longitude"})
    return data.dropna(subset=["latitude"], ignore_index=True)[
        ["time", "latitude", "longitude"]
    ]
