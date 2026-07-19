import pathlib
import uuid

from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .paths import INTERNAL_PICTURES_DIR

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def save_internal_picture(file: FileStorage) -> str:
    suffix = pathlib.Path(secure_filename(file.filename or "")).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported image type: {suffix!r}")

    filename = f"{uuid.uuid4().hex}{suffix}"
    path = INTERNAL_PICTURES_DIR() / filename
    file.save(path)

    try:
        with Image.open(path):
            pass
    except Exception as e:
        path.unlink(missing_ok=True)
        raise ValueError("Uploaded file is not a valid image.") from e

    return filename


def delete_internal_picture(filename: str) -> None:
    (INTERNAL_PICTURES_DIR() / filename).unlink(missing_ok=True)
