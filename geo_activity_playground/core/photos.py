import argparse
import datetime
import pathlib
import pprint
import zoneinfo

import exifread


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
        print(f"Extracted date: {date_time_original}")
        metadata["time"] = datetime.datetime.strptime(
            date_time_original, "%Y:%m:%d %H:%M:%S%z"
        ).astimezone(zoneinfo.ZoneInfo("UTC"))

    except KeyError:
        pass

    return metadata


def main_inspect_photo(options: argparse.Namespace) -> None:
    path: pathlib.Path = options.path
    metadata = get_metadata_from_image(path)
    pprint.pprint(metadata)
