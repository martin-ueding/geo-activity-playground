import argparse
import logging
import os
import pathlib
import pprint

from geo_activity_playground.webui.app import create_app

from .exif_handling import get_metadata_from_image, write_gps_to_image
from .matching import _lookup_location

logger = logging.getLogger(__name__)

_JPEG_SUFFIXES = {".jpg", ".jpeg"}


def main_annotate_photos(options: argparse.Namespace) -> None:
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


def register_main_annotate_photos(subparsers: argparse._SubParsersAction) -> None:
    subparser = subparsers.add_parser(
        "annotate-photos",
        help="Write GPS coordinates into EXIF of photos that lack location data",
    )
    subparser.add_argument(
        "paths",
        type=pathlib.Path,
        nargs="+",
        metavar="PHOTO",
        help="JPEG photo files to annotate",
    )
    subparser.set_defaults(func=main_annotate_photos)


def main_inspect_photo(options: argparse.Namespace) -> None:
    path: pathlib.Path = options.path
    metadata = get_metadata_from_image(path)
    pprint.pprint(metadata)


def register_main_inspect_photo(subparsers: argparse._SubParsersAction) -> None:
    subparser = subparsers.add_parser(
        "inspect-photo",
        help="Extract EXIF data from the image to see how it would be imported",
    )
    subparser.add_argument("path", type=pathlib.Path)
    subparser.set_defaults(func=main_inspect_photo)
