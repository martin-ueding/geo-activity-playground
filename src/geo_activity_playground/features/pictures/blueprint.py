import pathlib

from flask import Blueprint, Response, abort

from ...core.images import get_or_create_thumbnail
from ...core.paths import INTERNAL_PICTURES_DIR, PHOTOS_DIR, cache_dir

_KIND_DIRS = {
    "activity": (PHOTOS_DIR, "Photos"),
    "internal": (INTERNAL_PICTURES_DIR, "Internal Pictures"),
}


def make_pictures_blueprint() -> Blueprint:
    blueprint = Blueprint("pictures", __name__)

    @blueprint.route("/get/<kind>/<filename>/<int:size>.webp")
    def get(kind: str, filename: str, size: int) -> Response:
        if kind not in _KIND_DIRS:
            abort(404)
        root_dir, cache_subdir = _KIND_DIRS[kind]

        original_path = root_dir() / filename
        thumbnail_path = (
            cache_dir()
            / cache_subdir
            / f"size-{size}"
            / pathlib.Path(filename).with_suffix(".webp")
        )
        thumbnail_path = get_or_create_thumbnail(original_path, thumbnail_path, size)

        with open(thumbnail_path, "rb") as f:
            return Response(f.read(), mimetype="image/webp")

    return blueprint
