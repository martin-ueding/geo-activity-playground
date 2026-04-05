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
