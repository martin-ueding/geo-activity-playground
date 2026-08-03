import datetime
import io

import numpy as np
import sqlalchemy

from geo_activity_playground.core.datamodel import DB, DatabaseMaintenanceState
from geo_activity_playground.core.db_maintenance import run_database_maintenance_if_due
from geo_activity_playground.features.heatmap.cache import (
    blob_to_counts,
    compress_uncompressed_heatmap_cache_blobs,
    counts_to_blob,
)
from geo_activity_playground.features.heatmap.model import HeatmapTileCache


def _counts() -> np.ndarray:
    counts = np.zeros((256, 256), dtype=np.int32)
    counts[3, 4] = 17
    return counts


def _add_tile(tile_y: int, counts: bytes) -> None:
    entry = HeatmapTileCache()
    entry.zoom = 14
    entry.tile_x = 1
    entry.tile_y = tile_y
    entry.search_query_id = None
    entry.counts = counts
    entry.included_activity_ids = [1, 2]
    entry.num_activities = 2
    DB.session.add(entry)
    DB.session.commit()


def test_blob_round_trip_is_compressed():
    counts = _counts()
    blob = counts_to_blob(counts)
    assert len(blob) < counts.nbytes / 10
    np.testing.assert_array_equal(blob_to_counts(blob), counts)


def test_uncompressed_legacy_blob_is_still_readable():
    payload = io.BytesIO()
    np.save(payload, _counts(), allow_pickle=False)
    np.testing.assert_array_equal(blob_to_counts(payload.getvalue()), _counts())


def test_compress_uncompressed_blobs_rewrites_only_legacy_rows(app_context):
    payload = io.BytesIO()
    np.save(payload, _counts(), allow_pickle=False)
    _add_tile(1, payload.getvalue())
    _add_tile(2, counts_to_blob(_counts()))

    assert compress_uncompressed_heatmap_cache_blobs(batch_size=1) == 1
    assert compress_uncompressed_heatmap_cache_blobs() == 0

    for entry in DB.session.scalars(sqlalchemy.select(HeatmapTileCache)).all():
        np.testing.assert_array_equal(blob_to_counts(entry.counts), _counts())


def test_startup_records_a_maintenance_run(app_context):
    assert DB.session.get(DatabaseMaintenanceState, 1).last_run is not None


def test_maintenance_runs_once_per_interval(app_context):
    calls = []
    DB.session.get(DatabaseMaintenanceState, 1).last_run = None
    DB.session.commit()

    assert run_database_maintenance_if_due([lambda: calls.append(1)])
    assert calls == [1]
    assert not run_database_maintenance_if_due([lambda: calls.append(1)])
    assert calls == [1]

    state = DB.session.get(DatabaseMaintenanceState, 1)
    state.last_run = datetime.datetime.now() - datetime.timedelta(days=31)
    DB.session.commit()

    assert run_database_maintenance_if_due([lambda: calls.append(1)])
    assert calls == [1, 1]
