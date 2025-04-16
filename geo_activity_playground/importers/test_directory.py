import pathlib

from .directory import _get_metadata_from_path


def test_get_metadata_from_path() -> None:
    expected = {
        "kind": "Radfahrt",
        "equipment": "Bike 2019",
        "name": "Foo-Bar to Baz24",
    }
    actual = _get_metadata_from_path(
        pathlib.Path(
            "Activities/Radfahrt/Bike 2019/Foo-Bar to Baz24/2024-03-03-17-42-10 Something something.fit"
        ),
        [
            r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/(?P<name>[^/]+)/",
            r"(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ ]+(?P<name>[^/\.]+)(?:\.\w+)+$",
            r"(?P<kind>[^/]+)/[-\d_ ]+(?P<name>[^/\.]+)(?:\.\w+)+$",
        ],
    )
    assert actual == expected
