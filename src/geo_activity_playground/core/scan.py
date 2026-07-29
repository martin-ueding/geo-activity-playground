import sqlalchemy

from ..features.activity_photos.importer import import_photos_from_directory
from ..features.explorer.clustering import compute_tile_evolution
from ..features.hammerhead.source import HammerheadActivitySource
from ..features.segments.matching import find_matches
from ..features.segments.model import Segment
from ..features.strava.source import StravaActivitySource
from .activities import ActivityRepository
from .config import ConfigAccessor
from .datamodel import DB
from .sources import ActivitySource, DirectoryImportSource
from .tile_visits import compute_tile_visits_new

_ACTIVITY_SOURCES: list[ActivitySource] = [
    DirectoryImportSource(),
    StravaActivitySource(),
    HammerheadActivitySource(),
]


def scan_for_activities(
    repository: ActivityRepository,
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

        activity_source.import_activities(config_accessor, repository, begin, end)

    import_photos_from_directory()

    if len(repository) > 0:
        compute_tile_visits_new(repository)
        compute_tile_evolution(config_accessor.ui())

    for segment in DB.session.scalars(sqlalchemy.select(Segment)).all():
        find_matches(segment, config_accessor.activity_import())
