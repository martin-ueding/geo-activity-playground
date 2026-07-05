import argparse
import datetime
import logging
import os
import pathlib
import pprint
import zoneinfo

import exifread
import piexif
import sqlalchemy

from .datamodel import DB, Activity

logger = logging.getLogger(__name__)

_JPEG_SUFFIXES = {".jpg", ".jpeg"}


def ratio_to_decimal(numbers: list[exifread.utils.Ratio]) -> float:
    deg, min, sec = numbers.values
    return deg.decimal() + min.decimal() / 60 + sec.decimal() / 3600


def apply_ref_sign(value: float, ref: str, negative_refs: set[str]) -> float:
    if ref.strip().upper() in negative_refs:
        return -value
    return value


def get_metadata_from_image(path: pathlib.Path) -> dict:
    with open(path, "rb") as f:
        tags = exifread.process_file(f)
    metadata = {}
    try:
        latitude = ratio_to_decimal(tags["GPS GPSLatitude"])
        longitude = ratio_to_decimal(tags["GPS GPSLongitude"])
        latitude_ref = str(tags.get("GPS GPSLatitudeRef", "N"))
        longitude_ref = str(tags.get("GPS GPSLongitudeRef", "E"))
        metadata["latitude"] = apply_ref_sign(latitude, latitude_ref, {"S"})
        metadata["longitude"] = apply_ref_sign(longitude, longitude_ref, {"W"})
    except KeyError:
        pass
    try:
        date_time_original = str(tags["EXIF DateTimeOriginal"]) + str(
            tags.get("EXIF OffsetTime", "+00:00")
        ).replace(":", "")
        metadata["time"] = datetime.datetime.strptime(
            date_time_original, "%Y:%m:%d %H:%M:%S%z"
        ).astimezone(zoneinfo.ZoneInfo("UTC"))
    except KeyError:
        pass

    return metadata


def _decimal_to_dms_rational(value: float) -> tuple:
    d = int(abs(value))
    m = int((abs(value) - d) * 60)
    s_num = round((abs(value) - d - m / 60) * 3600 * 10000)
    return ((d, 1), (m, 1), (s_num, 10000))


def write_gps_to_image(path: pathlib.Path, lat: float, lon: float) -> None:
    exif_dict = piexif.load(str(path))
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = _decimal_to_dms_rational(lat)
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = _decimal_to_dms_rational(lon)
    piexif.insert(piexif.dump(exif_dict), str(path))


def _lookup_location(
    time: datetime.datetime,
) -> tuple[float, float] | None:
    activity = DB.session.scalar(
        sqlalchemy.select(Activity)
        .where(
            Activity.start.is_not(None),
            Activity.elapsed_time.is_not(None),
            Activity.start <= time,
        )
        .order_by(Activity.start.desc())
        .limit(1)
    )
    if activity is None or activity.start_utc + activity.elapsed_time < time:
        return None

    time_series = activity.time_series
    after = time_series.loc[time_series["time"] >= time]
    if after.empty:
        return None
    row = after.iloc[0]
    return float(row["latitude"]), float(row["longitude"])


def main_annotate_photos(options: argparse.Namespace) -> None:
    from ..webui.app import create_app

    os.chdir(options.basedir)
    database_path = pathlib.Path("database.sqlite")
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path.absolute()}")

    app = create_app(
        database_uri=f"sqlite:///{database_path.absolute()}",
        run_migrations=False,
    )

    paths: list[pathlib.Path] = options.paths
    with app.app_context():
        for path in paths:
            if path.suffix.lower() not in _JPEG_SUFFIXES:
                logger.warning(
                    "Skipping %s: only JPEG is supported for writing GPS EXIF.", path
                )
                continue

            metadata = get_metadata_from_image(path)

            if "latitude" in metadata:
                logger.info("Skipping %s: already has GPS coordinates.", path)
                continue

            if "time" not in metadata:
                logger.warning("Skipping %s: no DateTimeOriginal EXIF tag found.", path)
                continue

            location = _lookup_location(metadata["time"])
            if location is None:
                logger.warning(
                    "Skipping %s: no matching activity found for time %s.",
                    path,
                    metadata["time"],
                )
                continue

            lat, lon = location
            write_gps_to_image(path, lat, lon)
            logger.info("Annotated %s with lat=%.6f, lon=%.6f.", path, lat, lon)


def main_inspect_photo(options: argparse.Namespace) -> None:
    path: pathlib.Path = options.path
    metadata = get_metadata_from_image(path)
    pprint.pprint(metadata)
