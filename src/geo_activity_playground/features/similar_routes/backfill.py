import datetime
import logging

import sqlalchemy

from ...core.datamodel import DB, Activity
from .comparison import (
    ResampledTrack,
    resample_track,
    track_distance_quantiles,
    tracks_overlap,
)
from .model import QUANTILES, RouteDistance

logger = logging.getLogger(__name__)


class RouteDistanceBackfill:
    """Compares all pairs of activities, starting with the newest ones.

    Each step takes the next activity from newest to oldest and compares it in
    both directions with all newer activities. That way the recent activities
    are complete first and the older ones are filled in later.
    """

    def __init__(self) -> None:
        self._tracks: dict[int, ResampledTrack] = {}
        self._order: list[int] = []
        self._cursor = 0

    def run_step(self) -> bool:
        order = list(
            DB.session.scalars(
                sqlalchemy.select(Activity.id).order_by(
                    Activity.start.desc().nulls_last(), Activity.id.desc()
                )
            )
        )
        if order != self._order:
            self._order = order
            self._cursor = 0
            self._tracks = {
                id: track for id, track in self._tracks.items() if id in set(order)
            }

        while self._cursor < len(self._order):
            self._cursor += 1
            if self._compare_with_newer(self._cursor - 1):
                return True
        self._cursor = 0
        return False

    def _compare_with_newer(self, index: int) -> bool:
        anchor = self._order[index]
        compared_forward = set(
            DB.session.scalars(
                sqlalchemy.select(RouteDistance.reference_activity_id).where(
                    RouteDistance.activity_id == anchor
                )
            )
        )
        compared_backward = set(
            DB.session.scalars(
                sqlalchemy.select(RouteDistance.activity_id).where(
                    RouteDistance.reference_activity_id == anchor
                )
            )
        )
        missing = [
            other
            for other in self._order[:index]
            if other not in compared_forward or other not in compared_backward
        ]
        if not missing:
            return False

        now = datetime.datetime.now()
        track = self._track(anchor)
        rows = []
        for other in missing:
            other_track = self._track(other)
            overlap = tracks_overlap(track, other_track)
            for activity_id, reference_id, compared, a, b in [
                (anchor, other, compared_forward, track, other_track),
                (other, anchor, compared_backward, other_track, track),
            ]:
                if other in compared:
                    continue
                quantiles = (
                    track_distance_quantiles(a, b)
                    if overlap
                    else dict.fromkeys(QUANTILES)
                )
                rows.append(
                    {
                        "activity_id": activity_id,
                        "reference_activity_id": reference_id,
                        "checked_at": now,
                        **quantiles,
                    }
                )
        DB.session.execute(sqlalchemy.insert(RouteDistance), rows)
        DB.session.commit()
        logger.info(
            f"Compared activity {anchor} with {len(missing)} newer activities, {index} of {len(self._order)}."
        )
        return True

    def _track(self, activity_id: int) -> ResampledTrack:
        if activity_id not in self._tracks:
            activity = DB.session.get_one(Activity, activity_id)
            try:
                self._tracks[activity_id] = resample_track(activity.time_series)
            except OSError:
                self._tracks[activity_id] = ResampledTrack.empty()
        return self._tracks[activity_id]
