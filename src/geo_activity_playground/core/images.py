import pathlib

from PIL import Image, ImageOps


def get_or_create_thumbnail(
    original_path: pathlib.Path, thumbnail_path: pathlib.Path, size: int
) -> pathlib.Path:
    assert size < 5000
    if not thumbnail_path.exists():
        with Image.open(original_path) as im:
            im = ImageOps.exif_transpose(im)
            im = ImageOps.contain(im, (size, size))
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            im.save(thumbnail_path)
    return thumbnail_path
