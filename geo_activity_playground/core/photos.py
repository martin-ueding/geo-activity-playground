import argparse
import datetime
import pathlib
import pprint
import zoneinfo

import dateutil.parser
import exifread


def ratio_to_decimal(numbers: list[exifread.utils.Ratio]) -> float:
    deg, min, sec = numbers.values
    return deg.decimal() + min.decimal() / 60 + sec.decimal() / 3600


def get_metadata_from_image(path: pathlib.Path) -> dict:
    with open(path, "rb") as f:
        tags = exifread.process_file(f)
    metadata = {}
    try:
        metadata["latitude"] = ratio_to_decimal(tags["GPS GPSLatitude"])
        metadata["longitude"] = ratio_to_decimal(tags["GPS GPSLongitude"])
    except KeyError:
        pass
    try:
        metadata["time"] = dateutil.parser.parse(
            str(tags["EXIF DateTimeOriginal"])
            + str(tags.get("EXIF OffsetTime", "+00:00"))
        ).astimezone(zoneinfo.ZoneInfo("UTC"))
    except KeyError:
        pass

    return metadata


def main_inspect_photo(options: argparse.Namespace) -> None:
    path: pathlib.Path = options.path
    metadata = get_metadata_from_image(path)
    pprint.pprint(metadata)
