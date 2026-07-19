import json

import pytest
import sqlalchemy

from ..webui.app import create_app
from .config import ConfigAccessor, import_config_json
from .datamodel import DB, PrivacyZone


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(database_uri="sqlite:///:memory:", run_migrations=False)
    with app.app_context():
        yield


def test_ensure_exists_is_idempotent(app_context) -> None:
    accessor = ConfigAccessor()
    accessor.ensure_exists()
    accessor.ensure_exists()
    assert accessor.ui().explorer_zoom_levels == [14, 17]


def test_column_defaults_are_applied(app_context) -> None:
    accessor = ConfigAccessor()
    assert accessor.activity_import().time_diff_threshold_seconds == 30
    assert accessor.map().map_tile_url.startswith("https://")
    assert accessor.heart_rate().heart_rate_resting == 0


def test_optional_fields_default_to_null(app_context) -> None:
    accessor = ConfigAccessor()
    assert accessor.heart_rate().heart_rate_maximum is None
    assert accessor.map().map_style_url is None


def test_roundtrip_preserves_types(app_context) -> None:
    accessor = ConfigAccessor()
    accessor.heart_rate().birth_year = 1988
    accessor.ui().visible_table_columns = ["distance", "kind"]
    accessor.activity_import().kind_renames = {"Ride": "Bicycle"}
    accessor.activity_import().reliable_elevation_measurements = False
    accessor.save()

    # Force a database read so we exercise the stored representation, not the
    # in-memory identity map, mirroring what another worker process would see.
    DB.session.expire_all()
    other = ConfigAccessor()
    assert other.heart_rate().birth_year == 1988
    assert other.ui().visible_table_columns == ["distance", "kind"]
    assert other.activity_import().kind_renames == {"Ride": "Bicycle"}
    assert other.activity_import().reliable_elevation_measurements is False


def test_import_config_json_seeds_domains_and_privacy_zones(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "birth_year": 1990,
                "strava_client_id": 42,
                "map_tile_url": "https://example.org/{zoom}/{x}/{y}.png",
                "privacy_zones": {"Home": [[8.0, 50.0], [8.1, 50.0], [8.1, 50.1]]},
            }
        )
    )
    # The legacy file is imported while create_app() sets up a fresh database.
    app = create_app(database_uri="sqlite:///:memory:", run_migrations=False)
    with app.app_context():
        accessor = ConfigAccessor()
        assert accessor.heart_rate().birth_year == 1990
        assert accessor.strava().strava_client_id == 42
        assert accessor.map().map_tile_url == "https://example.org/{zoom}/{x}/{y}.png"
        zones = DB.session.scalars(sqlalchemy.select(PrivacyZone)).all()
        assert [zone.name for zone in zones] == ["Home"]


def test_import_config_json_is_skipped_once_rows_exist(app_context, tmp_path) -> None:
    accessor = ConfigAccessor()
    accessor.ensure_exists()
    (tmp_path / "config.json").write_text(json.dumps({"birth_year": 1990}))

    import_config_json(accessor)

    # Once the database holds settings it is authoritative; the file is ignored.
    assert accessor.heart_rate().birth_year is None
