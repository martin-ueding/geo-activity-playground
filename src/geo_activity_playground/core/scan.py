import pathlib

import sqlalchemy

from ..explorer.tile_visits import compute_tile_evolution, compute_tile_visits_new
from ..features.activity_photos.importer import import_photos_from_directory
from ..features.directory_import.importer import import_from_directory
from ..features.hammerhead.importer import import_from_hammerhead_api
from ..features.hammerhead.model import HammerheadAuth
from ..features.segments.matching import find_matches
from ..features.segments.model import Segment
from ..features.strava_api.importer import import_from_strava_api
from ..features.strava_checkout.importer import import_from_strava_checkout
from .activities import ActivityRepository
from .config import ConfigAccessor
from .datamodel import DB


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
    if pathlib.Path("Activities").exists():
        import_from_directory(
            repository, config_accessor.activity_import(), config_accessor.ui()
        )
    import_photos_from_directory()
    if pathlib.Path("Strava Export").exists():
        import_from_strava_checkout(config_accessor.activity_import())
    if config_accessor.strava().strava_client_code and not skip_strava:
        import_from_strava_api(config_accessor, repository, strava_begin, strava_end)
    hammerhead_auth = DB.session.scalar(sqlalchemy.select(HammerheadAuth).limit(1))
    if hammerhead_auth and hammerhead_auth.client_code and not skip_hammerhead:
        import_from_hammerhead_api(
            config_accessor.activity_import(),
            repository,
            hammerhead_begin,
            hammerhead_end,
        )

    if len(repository) > 0:
        compute_tile_visits_new(repository)
        compute_tile_evolution(config_accessor.ui())

    for segment in DB.session.scalars(sqlalchemy.select(Segment)).all():
        find_matches(segment, config_accessor.activity_import())
