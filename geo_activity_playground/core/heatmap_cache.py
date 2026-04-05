import datetime
import io
import json
import logging
import pathlib
import shutil

import numpy as np
import sqlalchemy
from tqdm import tqdm

from .datamodel import DB, HeatmapTileCache

logger = logging.getLogger(__name__)


def counts_to_blob(counts: np.ndarray) -> bytes:
    payload = io.BytesIO()
    np.save(payload, counts.astype(np.int32, copy=False), allow_pickle=False)
    return payload.getvalue()


def blob_to_counts(payload: bytes) -> np.ndarray:
    return np.load(io.BytesIO(payload), allow_pickle=False)


def get_tile_cache(
    zoom: int, tile_x: int, tile_y: int, search_query_id: int | None
) -> HeatmapTileCache | None:
    query = sqlalchemy.select(HeatmapTileCache).where(
        HeatmapTileCache.zoom == zoom,
        HeatmapTileCache.tile_x == tile_x,
        HeatmapTileCache.tile_y == tile_y,
    )
    if search_query_id is None:
        query = query.where(HeatmapTileCache.search_query_id.is_(None))
    else:
        query = query.where(HeatmapTileCache.search_query_id == search_query_id)
    return DB.session.scalars(query).first()


def write_tile_cache(
    zoom: int,
    tile_x: int,
    tile_y: int,
    search_query_id: int | None,
    counts: np.ndarray,
    included_activity_ids: set[int],
) -> None:
    cache_entry = get_tile_cache(zoom, tile_x, tile_y, search_query_id)
    if cache_entry is None:
        cache_entry = HeatmapTileCache()
        cache_entry.zoom = zoom
        cache_entry.tile_x = tile_x
        cache_entry.tile_y = tile_y
        cache_entry.search_query_id = search_query_id
        cache_entry.counts = b""
        cache_entry.included_activity_ids = []
        cache_entry.num_activities = 0
        DB.session.add(cache_entry)
    cache_entry.counts = counts_to_blob(counts)
    cache_entry.included_activity_ids = sorted(included_activity_ids)
    cache_entry.num_activities = len(included_activity_ids)
    cache_entry.last_used = datetime.datetime.now()
    DB.session.commit()


def touch_tile_cache(cache_entry: HeatmapTileCache) -> None:
    cache_entry.last_used = datetime.datetime.now()
    DB.session.commit()


def delete_heatmap_cache_for_query(search_query_id: int) -> int:
    result = DB.session.execute(
        sqlalchemy.delete(HeatmapTileCache).where(
            HeatmapTileCache.search_query_id == search_query_id
        )
    )
    DB.session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def delete_all_heatmap_cache() -> int:
    result = DB.session.execute(sqlalchemy.delete(HeatmapTileCache))
    DB.session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def delete_stale_heatmap_cache(older_than: datetime.datetime) -> int:
    result = DB.session.execute(
        sqlalchemy.delete(HeatmapTileCache).where(
            sqlalchemy.or_(
                HeatmapTileCache.last_used.is_(None),
                HeatmapTileCache.last_used < older_than,
            )
        )
    )
    DB.session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def import_legacy_heatmap_cache_from_filesystem() -> int:
    heatmap_cache_dir = pathlib.Path("Cache/Heatmap")
    if not heatmap_cache_dir.exists():
        return 0

    npy_paths = sorted(heatmap_cache_dir.glob("*/*/*.npy"))
    if not npy_paths:
        return 0

    imported = 0
    staged_entries: list[HeatmapTileCache] = []
    try:
        for npy_path in tqdm(
            npy_paths, desc="Import heatmap cache", delay=1, leave=False
        ):
            zoom = int(npy_path.parent.parent.name)
            tile_x = int(npy_path.parent.name)
            tile_y = int(npy_path.stem)

            existing = get_tile_cache(
                zoom=zoom, tile_x=tile_x, tile_y=tile_y, search_query_id=None
            )
            if existing is not None:
                continue

            counts = np.load(npy_path, allow_pickle=False)
            parsed_activities = _load_legacy_included_activity_ids(
                npy_path.with_suffix(".json")
            )
            staged_entries.append(
                _build_heatmap_cache_entry(
                    zoom=zoom,
                    tile_x=tile_x,
                    tile_y=tile_y,
                    counts=counts_to_blob(counts),
                    included_activity_ids=parsed_activities,
                )
            )

        if staged_entries:
            DB.session.add_all(staged_entries)
        DB.session.commit()
        imported = len(staged_entries)
    except Exception:
        DB.session.rollback()
        logger.exception(
            "Failed importing legacy heatmap cache from filesystem; keeping files in place."
        )
        return 0

    shutil.rmtree(heatmap_cache_dir)
    logger.info(
        "Imported %d legacy heatmap tiles into DB and removed %s.",
        imported,
        heatmap_cache_dir,
    )
    return imported


def _load_legacy_included_activity_ids(path: pathlib.Path) -> list[int]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return sorted(int(v) for v in payload)


def _build_heatmap_cache_entry(
    *,
    zoom: int,
    tile_x: int,
    tile_y: int,
    counts: bytes,
    included_activity_ids: list[int],
) -> HeatmapTileCache:
    entry = HeatmapTileCache()
    entry.zoom = zoom
    entry.tile_x = tile_x
    entry.tile_y = tile_y
    entry.search_query_id = None
    entry.counts = counts
    entry.included_activity_ids = included_activity_ids
    entry.num_activities = len(included_activity_ids)
    entry.last_used = None
    return entry
