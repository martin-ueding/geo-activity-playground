from .photos import apply_ref_sign, get_metadata_from_image


class _Ratio:
    def __init__(self, value: float) -> None:
        self._value = value

    def decimal(self) -> float:
        return self._value


class _ExifValue:
    def __init__(self, values: list[float]) -> None:
        self.values = [_Ratio(value) for value in values]


class _Ref:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


def test_apply_ref_sign() -> None:
    assert apply_ref_sign(1.23, "N", {"S"}) == 1.23
    assert apply_ref_sign(1.23, "s", {"S"}) == -1.23
    assert apply_ref_sign(4.56, "W", {"W"}) == -4.56


def test_get_metadata_from_image_respects_hemisphere(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"test")

    tags = {
        "GPS GPSLatitude": _ExifValue([10, 30, 0]),
        "GPS GPSLatitudeRef": _Ref("S"),
        "GPS GPSLongitude": _ExifValue([20, 15, 0]),
        "GPS GPSLongitudeRef": _Ref("W"),
    }

    monkeypatch.setattr(
        "geo_activity_playground.core.photos.exifread.process_file",
        lambda _: tags,
    )

    metadata = get_metadata_from_image(image_path)

    assert metadata["latitude"] == -10.5
    assert metadata["longitude"] == -20.25
