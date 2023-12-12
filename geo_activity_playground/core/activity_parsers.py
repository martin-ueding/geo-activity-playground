import datetime
import gzip
import pathlib
import tempfile
import xml

import dateutil.parser
import fitdecode
import gpxpy
import pandas as pd
import tcxreader.tcxreader
import xmltodict


class ActivityParseError(BaseException):
    pass


def read_activity(path: pathlib.Path) -> pd.DataFrame:
    suffixes = path.suffixes
    if suffixes[-1] == ".gz":
        opener = gzip.open
        file_type = suffixes[-2]
    else:
        opener = open
        file_type = suffixes[-1]

    if file_type == ".gpx":
        try:
            df = read_gpx_activity(path, opener)
        except gpxpy.gpx.GPXXMLSyntaxException as e:
            raise ActivityParseError("Syntax error while parsing GPX file") from e
    elif file_type == ".fit":
        df = read_fit_activity(path, opener)
    elif file_type == ".tcx":
        try:
            df = read_tcx_activity(path, opener)
        except xml.etree.ElementTree.ParseError as e:
            raise ActivityParseError("Syntax error in TCX file") from e
    elif file_type in [".kml", ".kmz"]:
        df = read_kml_activity(path, opener)
    else:
        raise ActivityParseError(f"Unsupported file format: {file_type}")

    if len(df):
        try:
            if df.time.dt.tz is not None:
                df.time = df.time.dt.tz_localize(None)
        except AttributeError as e:
            print(df)
            print(df.dtypes)
            types = {}
            for elem in df["time"]:
                t = str(type(elem))
                if t not in types:
                    types[t] = elem
            print(types)
            raise ActivityParseError(
                "It looks like the date parsing has gone wrong."
            ) from e
    df.name = path.stem.split(".")[0]
    return df


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
                        and fields.get("position_lat", None)
                        and fields.get("position_long", None)
                    ):
                        time = fields["timestamp"]
                        assert isinstance(time, datetime.datetime)
                        time = time.astimezone(datetime.timezone.utc)
                        row = {
                            "time": time,
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
                    if isinstance(point.time, datetime.datetime):
                        time = point.time
                    else:
                        time = dateutil.parser.parse(str(point.time))
                    assert isinstance(time, datetime.datetime)
                    time = time.astimezone(datetime.timezone.utc)
                    points.append((time, point.latitude, point.longitude))

    return pd.DataFrame(points, columns=["time", "latitude", "longitude"])


def read_tcx_activity(path: pathlib.Path, open) -> pd.DataFrame:
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

    with open(path, "rb") as f:
        content = f.read().strip()
    with tempfile.NamedTemporaryFile("wb", suffix=".tcx") as f:
        f.write(content)
        f.flush()
        data = tcx_reader.read(f.name)

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
