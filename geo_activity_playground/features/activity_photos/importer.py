import logging
import pathlib

import sqlalchemy

from ...core.datamodel import DB, Activity
from .exif_handling import get_metadata_from_image
from .model import Photo

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


def import_photos_from_directory() -> None:
    photos_dir = pathlib.Path("Photos")
    if not photos_dir.exists():
        return

    existing_filenames = set(
        DB.session.scalars(sqlalchemy.select(Photo.filename)).all()
    )

    new_count = 0
    skipped_count = 0

    for path in sorted(photos_dir.iterdir()):
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        if path.name in existing_filenames:
            skipped_count += 1
            continue

        metadata = get_metadata_from_image(path)

        if "time" not in metadata:
            logger.warning(
                "Photo %s has no EXIF DateTimeOriginal, skipping.", path.name
            )
            continue

        time = metadata["time"]

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
            logger.warning(
                "Photo %s is from %s but no matching activity found, skipping.",
                path.name,
                time,
            )
            continue

        if "latitude" not in metadata:
            time_series = activity.time_series
            row = time_series.loc[time_series["time"] >= time].iloc[0]
            metadata["latitude"] = row["latitude"]
            metadata["longitude"] = row["longitude"]

        photo = Photo(
            filename=path.name,
            time=time,
            latitude=metadata["latitude"],
            longitude=metadata["longitude"],
            activity=activity,
        )
        DB.session.add(photo)
        DB.session.commit()
        existing_filenames.add(path.name)
        new_count += 1

    logger.info("Photo inbox: %d new, %d skipped.", new_count, skipped_count)
