import argparse
import logging
import os
import pathlib

import coloredlogs

from .importers.strava_checkout import convert_strava_checkout
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.config import import_old_config
from geo_activity_playground.core.config import import_old_strava_config
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor
from geo_activity_playground.explorer.video import explorer_video_main
from geo_activity_playground.webui.app import web_ui_main
from geo_activity_playground.webui.upload.controller import scan_for_activities

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilities to work with recorded activities."
    )
    parser.set_defaults(func=lambda options: parser.print_help())
    parser.add_argument("--basedir", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument(
        "--loglevel",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
    )

    subparsers = parser.add_subparsers(
        description="The tools are organized in subcommands.", metavar="Command"
    )

    # subparser = subparsers.add_parser(
    #     "explorer",
    #     help="Generate GeoJSON/GPX files with explored and missing explorer tiles.",
    # )
    # subparser.set_defaults(
    #     func=lambda options: main_explorer(
    #         make_time_series_source(options.basedir)
    #     )
    # )

    subparser = subparsers.add_parser(
        "explorer-video", help="Generate video with explorer timeline."
    )
    subparser.set_defaults(func=lambda options: explorer_video_main())

    subparser = subparsers.add_parser(
        "convert-strava-checkout",
        help="Converts a Strava checkout to the structure used by this program.",
    )
    subparser.set_defaults(
        func=lambda options: convert_strava_checkout(
            options.checkout_path, options.playground_path
        )
    )
    subparser.add_argument("checkout_path", type=pathlib.Path)
    subparser.add_argument("playground_path", type=pathlib.Path)

    subparser = subparsers.add_parser("serve", help="Launch webserver")
    subparser.set_defaults(
        func=lambda options: web_ui_main(
            *make_activity_repository(options.basedir, options.skip_reload),
            host=options.host,
            port=options.port,
        )
    )
    subparser.add_argument(
        "--host", default="127.0.0.1", help="IP address to listen on"
    )
    subparser.add_argument(
        "--port", default=5000, type=int, help="the port to run listen on"
    )
    subparser.add_argument("--skip-reload", action=argparse.BooleanOptionalAction)

    subparser = subparsers.add_parser("cache", help="Cache stuff")
    subparser.set_defaults(func=lambda options: main_cache(options.basedir))

    options = parser.parse_args()
    coloredlogs.install(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=options.loglevel.upper(),
    )

    logging.getLogger("stravalib.protocol.ApiV3").setLevel(logging.WARNING)

    options.func(options)


def make_activity_repository(
    basedir: pathlib.Path, skip_reload: bool
) -> tuple[ActivityRepository, TileVisitAccessor, ConfigAccessor]:
    os.chdir(basedir)

    repository = ActivityRepository()
    tile_visit_accessor = TileVisitAccessor()
    config_accessor = ConfigAccessor()
    import_old_config(config_accessor)
    import_old_strava_config(config_accessor)

    if not skip_reload:
        scan_for_activities(repository, tile_visit_accessor, config_accessor())

    return repository, tile_visit_accessor, config_accessor


def main_cache(basedir: pathlib.Path) -> None:
    (repository, tile_visit_accessor, config_accessor) = make_activity_repository(
        basedir, False
    )


if __name__ == "__main__":
    main()
