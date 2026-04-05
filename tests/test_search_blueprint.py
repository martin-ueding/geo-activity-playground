import datetime
import json
import urllib.parse

import sqlalchemy

from geo_activity_playground.core.datamodel import (
    DB,
    HeatmapTileCache,
    StoredSearchQuery,
)


def test_delete_search_query_removes_favorite_cache(client, app):
    with app.app_context():
        stored = StoredSearchQuery(
            query_json=json.dumps({"name": "Morning Ride"}, sort_keys=True),
            is_favorite=True,
            last_used=datetime.datetime(2024, 1, 1),
        )
        DB.session.add(stored)
        DB.session.flush()
        cache = HeatmapTileCache(
            zoom=14,
            tile_x=1,
            tile_y=2,
            search_query_id=stored.id,
            counts=b"cache",
            included_activity_ids=[],
            num_activities=0,
            last_used=None,
        )
        DB.session.add(cache)
        DB.session.commit()

    response = client.get(
        "/search/delete-search-query?"
        + urllib.parse.urlencode({"name": "Morning Ride", "redirect": "/search"})
    )
    assert response.status_code == 302

    with app.app_context():
        updated = DB.session.scalar(
            sqlalchemy.select(StoredSearchQuery).where(
                StoredSearchQuery.query_json
                == json.dumps({"name": "Morning Ride"}, sort_keys=True)
            )
        )
        assert updated is not None
        assert updated.is_favorite is False
        assert (
            DB.session.scalar(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(HeatmapTileCache)
            )
            == 0
        )
