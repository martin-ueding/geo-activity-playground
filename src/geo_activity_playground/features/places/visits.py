import collections
import itertools

import sqlalchemy

from ...core.datamodel import DB
from .model import Stay

type PlaceId = int | None
type Leg = tuple[PlaceId, PlaceId]


def visit_sequence(stay_place_ids: list[PlaceId]) -> list[PlaceId]:
    """The visits of an activity from the places of its stays in order.

    The first and last stays are the start and end, which are kept also when
    they don't match a place. Unmatched intermediate stays are dropped.
    Consecutive visits of the same place are merged, except for a start and an
    end without a visit in between, which form a round trip.
    """
    if len(stay_place_ids) < 2:
        return []
    start, *intermediates, end = stay_place_ids
    visits = [start]
    for place_id in intermediates:
        if place_id is not None and place_id != visits[-1]:
            visits.append(place_id)
    if len(visits) == 1 or visits[-1] != end:
        visits.append(end)
    return visits


def count_legs(activity_ids: set[int] | None) -> collections.Counter[Leg]:
    query = sqlalchemy.select(Stay.activity_id, Stay.place_id).order_by(
        Stay.activity_id, Stay.sequence
    )
    if activity_ids is not None:
        query = query.where(Stay.activity_id.in_(activity_ids))
    legs: collections.Counter[Leg] = collections.Counter()
    for _, rows in itertools.groupby(
        DB.session.execute(query), key=lambda row: row.activity_id
    ):
        visits = visit_sequence([row.place_id for row in rows])
        legs.update(itertools.pairwise(visits))
    return legs
