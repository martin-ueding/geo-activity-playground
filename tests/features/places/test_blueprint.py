import collections

import sqlalchemy
from flask import Flask

from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.core.meta_search import activity_ids_for_search
from geo_activity_playground.features.places.blueprint import (
    _components,
    _undirected_edges,
)
from geo_activity_playground.features.places.model import Place, Stay, StayKind


def _first_start(app: Flask) -> tuple[int, float, float]:
    with app.app_context():
        stay = DB.session.scalar(
            sqlalchemy.select(Stay)
            .where(Stay.kind == StayKind.START)
            .order_by(Stay.activity_id)
            .limit(1)
        )
        assert stay is not None, "the import must detect stays"
        return stay.activity_id, stay.latitude, stay.longitude


def test_every_imported_activity_has_start_and_end(seeded_app: Flask) -> None:
    with seeded_app.app_context():
        for activity in DB.session.scalars(sqlalchemy.select(Activity)):
            kinds = [stay.kind for stay in activity.stays]
            assert kinds[0] == StayKind.START
            assert kinds[-1] == StayKind.END


def test_place_lifecycle(seeded_app: Flask, seeded_client) -> None:
    activity_id, latitude, longitude = _first_start(seeded_app)

    response = seeded_client.post(
        "/places/new",
        data={"name": "Home", "latitude": latitude, "longitude": longitude},
    )
    assert response.status_code == 302

    with seeded_app.app_context():
        place = DB.session.scalar(sqlalchemy.select(Place))
        assert place is not None
        place_id = place.id
        assert activity_id in activity_ids_for_search({"start_place": place_id})
        assert activity_id in activity_ids_for_search({"stop_place": place_id})

    response = seeded_client.get(f"/places/?start_place={place_id}")
    assert response.status_code == 200
    assert "Home" in response.text

    response = seeded_client.post(
        f"/places/{place_id}/update",
        data={"name": "Far away", "latitude": 0.0, "longitude": 0.0},
    )
    assert response.status_code == 302
    with seeded_app.app_context():
        assert activity_ids_for_search({"start_place": place_id}) == set()

    response = seeded_client.post(f"/places/{place_id}/delete")
    assert response.status_code == 302
    with seeded_app.app_context():
        assert DB.session.scalar(sqlalchemy.select(Place)) is None


def test_place_without_name_is_rejected(seeded_app: Flask, seeded_client) -> None:
    response = seeded_client.post(
        "/places/new", data={"name": " ", "latitude": 1.0, "longitude": 2.0}
    )
    assert response.status_code == 302
    with seeded_app.app_context():
        assert DB.session.scalar(sqlalchemy.select(Place)) is None


def test_map_edges_combine_both_directions() -> None:
    legs = collections.Counter(
        {(1, 2): 3, (2, 1): 2, (1, 1): 4, (None, 1): 5, (3, None): 1, (2, 3): 1}
    )

    assert _undirected_edges(legs) == {(1, 2): 5, (2, 3): 1}


def test_components_split_at_unknown_places() -> None:
    legs = collections.Counter(
        {(1, 2): 3, (2, 1): 2, (None, 1): 5, (3, None): 1, (3, 4): 1, (None, None): 2}
    )

    assert _components(legs) == [
        {(1, 2): 3, (2, 1): 2, (None, 1): 5},
        {(3, None): 1, (3, 4): 1},
        {(None, None): 2},
    ]


def test_components_keep_each_place_in_one_component() -> None:
    legs = collections.Counter(
        {(1, 2): 1, (2, 3): 1, (3, 4): 1, (4, 5): 1, (1, 5): 1, (5, 6): 1, (2, 6): 1}
    )

    assert _components(legs) == [legs]
