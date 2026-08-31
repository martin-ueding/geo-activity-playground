import logging

import sqlalchemy
from tqdm import tqdm

from ..features.activity_photos.importer import import_photos_from_directory
from ..features.explorer.clustering import compute_tile_evolution
from ..features.explorer.filtered import delete_outdated_filtered_cluster_cache
from ..features.hammerhead.source import HammerheadActivitySource
from ..features.segments.matching import find_matches
from ..features.segments.model import Segment
from ..features.strava.source import StravaActivitySource
from .config import ConfigAccessor
from .datamodel import DB, Activity, count_activities
from .pipeline import refresh_stale_enrichments
from .sources import ActivitySource, DirectoryImportSource
from .tile_visits import compute_tile_visits_new

logger = logging.getLogger(__name__)

_ACTIVITY_SOURCES: list[ActivitySource] = [
    DirectoryImportSource(),
    StravaActivitySource(),
    HammerheadActivitySource(),
]


def scan_for_activities(
    config_accessor: ConfigAccessor,
    strava_begin: str | None = None,
    strava_end: str | None = None,
    skip_strava: bool = False,
    hammerhead_begin: str | None = None,
    hammerhead_end: str | None = None,
    skip_hammerhead: bool = False,
) -> None:
    for activity_source in _ACTIVITY_SOURCES:
        if not activity_source.is_enabled(config_accessor):
            continue
        if activity_source.source == "strava" and skip_strava:
            continue
        if activity_source.source == "hammerhead" and skip_hammerhead:
            continue

        if activity_source.source == "strava":
            begin = strava_begin
            end = strava_end
        elif activity_source.source == "hammerhead":
            begin = hammerhead_begin
            end = hammerhead_end
        else:
            begin = None
            end = None

        activity_source.import_activities(config_accessor, begin, end)

    refresh_stale_ingests(config_accessor)
    refresh_stale_enrichments(config_accessor.activity_import())

    import_photos_from_directory()

    if count_activities() > 0:
        compute_tile_visits_new()
        compute_tile_evolution(config_accessor.ui())
        # New activity tiles invalidate every cached filtered state.
        delete_outdated_filtered_cluster_cache()

    for segment in DB.session.scalars(sqlalchemy.select(Segment)).all():
        find_matches(segment, config_accessor.activity_import())


def source_for_activity(activity: Activity) -> ActivitySource | None:
    """The source that an activity came from, if it is still known."""
    for activity_source in _ACTIVITY_SOURCES:
        if activity_source.source == activity.source:
            return activity_source
    return None


def refresh_stale_ingests(
    config_accessor: ConfigAccessor, force: bool = False
) -> tuple[int, int]:
    """Run the ingest stage again where the source's code has moved on.

    With `force`, every activity is re-parsed regardless of its stamp, which is what
    the maintenance action offers. Only sources that kept their artifact can do this,
    and they say so by returning False when it is gone. An activity that cannot be
    re-parsed is counted as skipped rather than causing a request to a remote API
    that the user did not ask for.

    Returns the number of activities re-parsed and the number skipped.
    """
    reparsed = skipped = 0
    for activity_source in _ACTIVITY_SOURCES:
        query = sqlalchemy.select(Activity).filter(
            Activity.source == activity_source.source
        )
        if not force:
            query = query.filter(
                Activity.ingest_version < activity_source.ingest_version
            )
        candidates = DB.session.scalars(query).all()
        if not candidates:
            continue
        logger.info(
            "Re-ingesting %d activities of source %r.",
            len(candidates),
            activity_source.source,
        )
        for activity in tqdm(
            candidates, desc=f"Re-parsing {activity_source.source} activities", delay=1
        ):
            if activity_source.reingest(activity, config_accessor):
                reparsed += 1
            else:
                skipped += 1
    return reparsed, skipped
