import logging
from collections.abc import Collection, Mapping

import sqlalchemy
from tqdm import tqdm

from ..features.activity_photos.importer import import_photos_from_directory
from ..features.explorer.clustering import compute_tile_evolution
from ..features.explorer.filtered import delete_outdated_filtered_cluster_cache
from ..features.garmin.source import GarminActivitySource
from ..features.hammerhead.source import HammerheadActivitySource
from ..features.segments.matching import find_matches
from ..features.segments.model import Segment
from ..features.strava.source import (
    StravaApiActivitySource,
    StravaCheckoutActivitySource,
)
from .config import ConfigAccessor
from .datamodel import DB, Activity, count_activities
from .pipeline import refresh_stale_enrichments
from .sources import ActivitySource, DateRange, DirectoryImportSource
from .tile_visits import compute_tile_visits_new

logger = logging.getLogger(__name__)

_ACTIVITY_SOURCES: list[ActivitySource] = [
    DirectoryImportSource(),
    StravaCheckoutActivitySource(),
    StravaApiActivitySource(),
    HammerheadActivitySource(),
    GarminActivitySource(),
]


def remote_families() -> list[str]:
    """The families of all sources that reach out beyond the local directory."""
    return sorted(
        {
            activity_source.family
            for activity_source in _ACTIVITY_SOURCES
            if not isinstance(activity_source, DirectoryImportSource)
        }
    )


def scan_for_activities(
    config_accessor: ConfigAccessor,
    date_ranges: Mapping[str, DateRange] | None = None,
    skip: Collection[str] = (),
) -> None:
    """Import from all enabled sources.

    The keys of `date_ranges` and the entries of `skip` are source families.
    """
    date_ranges = date_ranges or {}
    for activity_source in _ACTIVITY_SOURCES:
        if not activity_source.is_enabled(config_accessor):
            continue
        if activity_source.family in skip:
            continue

        date_range = date_ranges.get(activity_source.family, DateRange())
        activity_source.import_activities(
            config_accessor, date_range.begin, date_range.end
        )

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
