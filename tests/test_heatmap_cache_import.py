import json
import os
import pathlib

import numpy as np
import sqlalchemy

from geo_activity_playground.core.datamodel import DB, HeatmapTileCache
from geo_activity_playground.webui.app import create_app


def test_startup_imports_legacy_heatmap_cache_and_removes_directory(
    tmp_path: pathlib.Path,
):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        (tmp_path / "config.json").write_text(
            json.dumps({"heatmap_cache_min_activities": 2}), encoding="utf-8"
        )
        legacy_dir = tmp_path / "Cache" / "Heatmap" / "14" / "123"
        legacy_dir.mkdir(parents=True)
        counts = np.zeros((256, 256), dtype=np.int32)
        counts[0, 0] = 7
        np.save(legacy_dir / "456.npy", counts, allow_pickle=False)
        (legacy_dir / "456.json").write_text("[11, 42]", encoding="utf-8")

        app = create_app(
            database_uri="sqlite:///:memory:",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        with app.app_context():
            assert (
                DB.session.scalar(
                    sqlalchemy.select(sqlalchemy.func.count()).select_from(
                        HeatmapTileCache
                    )
                )
                == 1
            )
            entry = DB.session.scalars(sqlalchemy.select(HeatmapTileCache)).one()
            assert entry.zoom == 14
            assert entry.tile_x == 123
            assert entry.tile_y == 456
            assert entry.search_query_id is None
            assert entry.included_activity_ids == [11, 42]
            assert entry.num_activities == 2
            assert entry.last_used is None

        assert not (tmp_path / "Cache" / "Heatmap").exists()
    finally:
        os.chdir(original_cwd)


def test_startup_keeps_legacy_directory_when_import_fails(tmp_path: pathlib.Path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        legacy_dir = tmp_path / "Cache" / "Heatmap" / "14" / "123"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "456.npy").write_bytes(b"this-is-not-a-valid-npy")

        app = create_app(
            database_uri="sqlite:///:memory:",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        with app.app_context():
            assert (
                DB.session.scalar(
                    sqlalchemy.select(sqlalchemy.func.count()).select_from(
                        HeatmapTileCache
                    )
                )
                == 0
            )

        assert (tmp_path / "Cache" / "Heatmap").exists()
    finally:
        os.chdir(original_cwd)


def test_startup_drops_cache_entries_below_minimum_activities(tmp_path: pathlib.Path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        database_path = tmp_path / "cache-test.sqlite"
        app = create_app(
            database_uri=f"sqlite:///{database_path}",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        with app.app_context():
            small = HeatmapTileCache()
            small.zoom = 14
            small.tile_x = 1
            small.tile_y = 1
            small.search_query_id = None
            small.counts = b"small"
            small.included_activity_ids = [1, 2]
            small.num_activities = 2
            small.last_used = None

            large = HeatmapTileCache()
            large.zoom = 14
            large.tile_x = 1
            large.tile_y = 2
            large.search_query_id = None
            large.counts = b"large"
            large.included_activity_ids = [1, 2, 3, 4, 5]
            large.num_activities = 5
            large.last_used = None

            DB.session.add_all([small, large])
            DB.session.commit()

        (tmp_path / "config.json").write_text(
            json.dumps({"heatmap_cache_min_activities": 5}), encoding="utf-8"
        )
        app = create_app(
            database_uri=f"sqlite:///{database_path}",
            secret_key="test-secret-key",
            run_migrations=False,
        )
        with app.app_context():
            caches = DB.session.scalars(sqlalchemy.select(HeatmapTileCache)).all()
            assert len(caches) == 1
            assert caches[0].tile_y == 2
            assert caches[0].num_activities == 5
    finally:
        os.chdir(original_cwd)
