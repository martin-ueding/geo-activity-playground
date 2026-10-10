from collections.abc import Sequence

import numpy as np
import sqlalchemy

from ...core.coordinates import get_distance
from ...core.datamodel import DB
from .model import PLACE_RADIUS_M, Place, Stay

CHUNK_SIZE = 10_000


def nearest_place_ids(
    latitudes: Sequence[float],
    longitudes: Sequence[float],
    places: Sequence[tuple[int, float, float]],
) -> list[int | None]:
    """The id of the nearest place within the radius for every position."""
    if not places:
        return [None] * len(latitudes)
    place_ids, place_lat, place_lon = map(np.array, zip(*places))
    result: list[int | None] = []
    for begin in range(0, len(latitudes), CHUNK_SIZE):
        lat = np.asarray(latitudes[begin : begin + CHUNK_SIZE])
        lon = np.asarray(longitudes[begin : begin + CHUNK_SIZE])
        distances = get_distance(
            lat[:, None], lon[:, None], place_lat[None, :], place_lon[None, :]
        )
        nearest = distances.argmin(axis=1)
        within = distances[np.arange(len(lat)), nearest] <= PLACE_RADIUS_M
        result.extend(
            int(place_ids[index]) if is_within else None
            for index, is_within in zip(nearest, within)
        )
    return result


def load_places() -> list[tuple[int, float, float]]:
    return [
        (id, latitude, longitude)
        for id, latitude, longitude in DB.session.execute(
            sqlalchemy.select(Place.id, Place.latitude, Place.longitude)
        )
    ]


def match_stays(stays: Sequence[Stay]) -> None:
    place_ids = nearest_place_ids(
        [stay.latitude for stay in stays],
        [stay.longitude for stay in stays],
        load_places(),
    )
    for stay, place_id in zip(stays, place_ids):
        stay.place_id = place_id


def rematch_all_stays() -> None:
    rows = DB.session.execute(
        sqlalchemy.select(Stay.id, Stay.latitude, Stay.longitude, Stay.place_id)
    ).all()
    place_ids = nearest_place_ids(
        [row.latitude for row in rows], [row.longitude for row in rows], load_places()
    )
    changes = [
        {"id": row.id, "place_id": place_id}
        for row, place_id in zip(rows, place_ids)
        if row.place_id != place_id
    ]
    if changes:
        DB.session.execute(sqlalchemy.update(Stay), changes)
    DB.session.commit()
