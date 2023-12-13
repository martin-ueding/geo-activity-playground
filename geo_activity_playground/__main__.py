import argparse
import logging
import os
import pathlib
import sys

import coloredlogs

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import embellish_time_series
from geo_activity_playground.core.cache_migrations import apply_cache_migrations
from geo_activity_playground.core.config import get_config
from geo_activity_playground.explorer.tile_visits import compute_tile_evolution
from geo_activity_playground.explorer.tile_visits import compute_tile_visits
from geo_activity_playground.explorer.video import explorer_video_main
from geo_activity_playground.heatmap import generate_heatmaps_per_cluster
from geo_activity_playground.importers.directory import import_from_directory
from geo_activity_playground.importers.strava_api import import_from_strava_api
from geo_activity_playground.webui.app import webui_main

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
        "heatmaps", help="Generate heatmaps from activities"
    )
    subparser.set_defaults(
        func=lambda options: generate_heatmaps_per_cluster(
            make_activity_repository(options.basedir)
        )
    )

    subparser = subparsers.add_parser("serve", help="Launch webserver")
    subparser.set_defaults(
        func=lambda options: webui_main(
            make_activity_repository(options.basedir),
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

    subparser = subparsers.add_parser("cache", help="Cache stuff")
    subparser.set_defaults(
        func=lambda options: make_activity_repository(options.basedir)
    )

    options = parser.parse_args()
    coloredlogs.install(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=options.loglevel.upper(),
    )

    logging.getLogger("stravalib.protocol.ApiV3").setLevel(logging.WARNING)

    options.func(options)


def make_activity_repository(basedir: pathlib.Path) -> ActivityRepository:
    os.chdir(basedir)
    apply_cache_migrations()
    config = get_config()
    if pathlib.Path("Activities").exists():
        import_from_directory()
    elif config:
        if "strava" in config:
            import_from_strava_api()
    else:
        logger.error(
            "You need to either have (1) an “Activity” directory with GPX/FIT/TCX/KML files in there or (2) a “config.toml” with information for the Strava API (see https://martin-ueding.github.io/geo-activity-playground/getting-started/using-strava-api/)."
        )
        sys.exit(1)
    repository = ActivityRepository()
    embellish_time_series(repository)
    compute_tile_visits(repository)
    compute_tile_evolution()
    return repository
