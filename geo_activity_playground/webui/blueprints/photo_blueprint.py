import datetime
import pathlib
import uuid

import dateutil.parser
import exifread
import geojson
import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for
from PIL import Image
from PIL import ImageOps

from ...core.config import ConfigAccessor
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.datamodel import Photo
from ...core.paths import PHOTOS_DIR
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes


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
        metadata["time"] = datetime.datetime.strptime(
            str(tags["EXIF DateTimeOriginal"]), "%Y:%m:%d %H:%M:%S"
        )
    except KeyError:
        pass

    return metadata


def make_photo_blueprint(
    config_accessor: ConfigAccessor, authenticator: Authenticator, flasher: Flasher
) -> Blueprint:
    blueprint = Blueprint("photo", __name__, template_folder="templates")

    @blueprint.route("/get/<int:id>/<int:size>.webp")
    def get(id: int, size: int) -> Response:
        assert size < 5000
        photo = DB.session.get_one(Photo, id)

        original_path = PHOTOS_DIR() / "original" / photo.path
        small_path = PHOTOS_DIR() / f"size-{size}" / photo.path.with_suffix(".webp")

        if not small_path.exists():
            with Image.open(original_path) as im:
                target_size = (size, size)
                im = ImageOps.contain(im, target_size)
                small_path.parent.mkdir(exist_ok=True)
                im.save(small_path)

        with open(small_path, "rb") as f:
            return Response(f.read(), mimetype="image/webp")

    @blueprint.route("/map")
    def map() -> str:
        return render_template("photo/map.html.j2")

    @blueprint.route("/map-for-all/photos.geojson")
    def map_for_all() -> Response:
        photos = DB.session.scalars(sqlalchemy.select(Photo)).all()
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.Point((photo.longitude, photo.latitude)),
                    properties={
                        "photo_id": photo.id,
                        "url_marker": url_for(".get", id=photo.id, size=128),
                        "url_popup": url_for(".get", id=photo.id, size=512),
                        "url_full": url_for(".get", id=photo.id, size=4096),
                    },
                )
                for photo in photos
            ]
        )
        return Response(
            geojson.dumps(fc, sort_keys=True, indent=2, ensure_ascii=False),
            mimetype="application/json",
        )

    @blueprint.route("/map-for-activity/<int:activity_id>/photos.geojson")
    def map_for_activity(activity_id: int) -> Response:
        activity = DB.session.get_one(Activity, activity_id)
        fc = geojson.FeatureCollection(
            features=[
                geojson.Feature(
                    geometry=geojson.Point((photo.longitude, photo.latitude)),
                    properties={
                        "photo_id": photo.id,
                        "url_marker": url_for(".get", id=photo.id, size=128),
                        "url_popup": url_for(".get", id=photo.id, size=512),
                        "url_full": url_for(".get", id=photo.id, size=4096),
                    },
                )
                for photo in activity.photos
            ]
        )
        return Response(
            geojson.dumps(fc, sort_keys=True, indent=2, ensure_ascii=False),
            mimetype="application/json",
        )

    @blueprint.route("/new", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def new() -> Response:
        if request.method == "POST":
            # check if the post request has the file part
            if "file" not in request.files:
                flasher.flash_message(
                    "No file could be found. Did you select a file?", FlashTypes.WARNING
                )
                return redirect(url_for(".new"))

            file = request.files["file"]
            # If the user does not select a file, the browser submits an
            # empty file without a filename.
            if file.filename == "":
                flasher.flash_message("No selected file.", FlashTypes.WARNING)
                return redirect(url_for(".new"))
            if not file:
                flasher.flash_message("Empty file uploaded.", FlashTypes.WARNING)
                return redirect(url_for(".new"))

            filename = str(uuid.uuid4()) + pathlib.Path(file.filename).suffix
            path = PHOTOS_DIR() / "original" / filename
            path.parent.mkdir(exist_ok=True)
            file.save(path)
            metadata = get_metadata_from_image(path)

            if "time" not in metadata:
                flasher.flash_message(
                    "Your image doesn't have the EXIF attribute 'EXIF DateTimeOriginal' and hence cannot be dated.",
                    FlashTypes.DANGER,
                )
                return redirect(url_for(".new"))
            time: datetime.datetime = metadata["time"]

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
            if activity is None or activity.start + activity.elapsed_time < time:
                flasher.flash_message(
                    f"Your image is from {time} but no activity could be found. Please first upload an activity or fix the time in the photo",
                    FlashTypes.DANGER,
                )
            print(activity)

            if "latitude" not in metadata:
                time_series = activity.time_series
                print(time_series)
                row = time_series.loc[time_series["time"] >= time].iloc[0]
                metadata["latitude"] = row["latitude"]
                metadata["longitude"] = row["longitude"]

            photo = Photo(
                filename=filename,
                time=time,
                latitude=metadata["latitude"],
                longitude=metadata["longitude"],
                activity=activity,
            )

            DB.session.add(photo)
            DB.session.commit()

            return redirect(f"/activity/{activity.id}")
        else:
            return render_template("photo/new.html.j2")

    return blueprint
