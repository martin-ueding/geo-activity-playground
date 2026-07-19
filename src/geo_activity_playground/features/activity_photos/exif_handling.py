import datetime
import pathlib
import zoneinfo

import exifread
import piexif


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
