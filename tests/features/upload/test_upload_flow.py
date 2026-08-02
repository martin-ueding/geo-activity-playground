import io
import pathlib
import urllib.parse

import sqlalchemy
from flask import Flask

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity, Kind, Tag

GPX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>{name}</name>
    <desc>{description}</desc>
    <type>{kind}</type>
    <trkseg>
      <trkpt lat="51.49" lon="3.61"><time>2024-05-10T10:00:0{offset}Z</time></trkpt>
      <trkpt lat="51.50" lon="3.62"><time>2024-05-10T10:01:0{offset}Z</time></trkpt>
      <trkpt lat="51.51" lon="3.63"><time>2024-05-10T10:02:0{offset}Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def _gpx(name: str = "In-file name", kind: str = "Hiking", offset: int = 0) -> bytes:
    return GPX_TEMPLATE.format(
        name=name, description="In-file description", kind=kind, offset=offset
    ).encode()


def _upload(client, files: list[tuple[bytes, str]], directory: str = "Activities"):
    return client.post(
        "/upload/receive",
        data={
            "directory": directory,
            "file": [(io.BytesIO(content), name) for content, name in files],
        },
        content_type="multipart/form-data",
    )


def _redirect_ids(response) -> list[str]:
    query = urllib.parse.urlparse(response.headers["Location"]).query
    return urllib.parse.parse_qs(query).get("id", [])


def test_upload_redirects_to_bulk_edit_with_all_ids(app: Flask) -> None:
    client = app.test_client()
    response = _upload(
        client,
        [(_gpx(offset=0), "first.gpx"), (_gpx(offset=1), "second.gpx")],
    )

    assert response.status_code == 302
    assert urllib.parse.urlparse(response.headers["Location"]).path == (
        "/activity/bulk-edit"
    )
    assert len(_redirect_ids(response)) == 2

    with app.app_context():
        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(Activity.id)))
            == 2
        )


def test_import_records_the_file_derived_metadata(app: Flask) -> None:
    client = app.test_client()
    with app.app_context():
        config_accessor = ConfigAccessor()
        config_accessor.activity_import().metadata_extraction_regexes = [
            r"(?P<name>[^/]+)\.gpx$"
        ]
        config_accessor.save()

    _upload(client, [(_gpx(name="In-file name"), "Name from the file name.gpx")])

    with app.app_context():
        activity = DB.session.scalar(sqlalchemy.select(Activity))
        assert activity is not None
        # The path regex wins for the effective name, but the file layer is kept.
        assert activity.name == "Name from the file name"
        assert activity.name_from_file == "In-file name"
        assert activity.kind_from_file == "Hiking"
        assert activity.description == "In-file description"


def test_bulk_edit_shows_both_name_candidates(app: Flask) -> None:
    client = app.test_client()
    with app.app_context():
        config_accessor = ConfigAccessor()
        config_accessor.activity_import().metadata_extraction_regexes = [
            r"(?P<name>[^/]+)\.gpx$"
        ]
        config_accessor.save()

    response = _upload(client, [(_gpx(name="In-file name"), "Path name.gpx")])
    page = client.get(response.headers["Location"])

    assert page.status_code == 200
    assert b'data-name-file="In-file name"' in page.data
    assert b'data-name-path="Path name"' in page.data


def test_bulk_edit_writes_all_fields(app: Flask) -> None:
    client = app.test_client()
    response = _upload(
        client,
        [(_gpx(offset=0), "first.gpx"), (_gpx(offset=1), "second.gpx")],
    )
    ids = _redirect_ids(response)

    with app.app_context():
        tag = Tag(tag="commute")
        kind = Kind(name="Cycling")
        DB.session.add_all([tag, kind])
        DB.session.commit()
        tag_id, kind_id = tag.id, kind.id

    form = {"id": ids}
    for index, id in enumerate(ids):
        form[f"name-{id}"] = f"Renamed {index}"
        form[f"description-{id}"] = f"Description {index}"
        form[f"kind-{id}"] = str(kind_id)
        form[f"tag-{id}"] = str(tag_id)

    post = client.post(
        "/activity/bulk-edit?" + urllib.parse.urlencode([("id", id) for id in ids]),
        data=form,
    )
    assert post.status_code == 302

    with app.app_context():
        for index, id in enumerate(ids):
            activity = DB.session.get_one(Activity, int(id))
            assert activity.name == f"Renamed {index}"
            assert activity.description == f"Description {index}"
            assert activity.kind.name == "Cycling"
            assert [t.tag for t in activity.tags] == ["commute"]


def test_bulk_edit_ignores_unknown_ids(seeded_client) -> None:
    assert seeded_client.get("/activity/bulk-edit?id=999999").status_code == 200


def test_colliding_upload_is_stored_under_its_content_hash(
    app: Flask, playground: pathlib.Path
) -> None:
    client = app.test_client()
    _upload(client, [(_gpx(offset=0), "ride.gpx")])
    response = _upload(client, [(_gpx(offset=1), "ride.gpx")])

    assert len(_redirect_ids(response)) == 1
    stored = {p.name for p in (playground / "Activities").iterdir()}
    assert "ride.gpx" in stored
    hashed = stored - {"ride.gpx"}
    assert len(hashed) == 1
    assert len(hashed.pop()) == 64 + len(".gpx")

    with app.app_context():
        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(Activity.id)))
            == 2
        )


def test_identical_upload_is_skipped_without_leaving_a_temporary_file(
    app: Flask, playground: pathlib.Path
) -> None:
    client = app.test_client()
    _upload(client, [(_gpx(), "ride.gpx")])
    response = _upload(client, [(_gpx(), "ride.gpx")])

    # Nothing new was imported, so the flow returns to the upload page.
    assert urllib.parse.urlparse(response.headers["Location"]).path == "/upload/"
    assert [p.name for p in (playground / "Activities").iterdir()] == ["ride.gpx"]

    with app.app_context():
        assert (
            DB.session.scalar(sqlalchemy.select(sqlalchemy.func.count(Activity.id)))
            == 1
        )
