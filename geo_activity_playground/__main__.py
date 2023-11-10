import argparse
import os
import pathlib

import coloredlogs

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.sources import TimeSeriesSource
from geo_activity_playground.explorer.grid_file import get_border_tiles
from geo_activity_playground.explorer.grid_file import get_explored_tiles
from geo_activity_playground.explorer.grid_file import make_grid_file_geojson
from geo_activity_playground.explorer.grid_file import make_grid_file_gpx
from geo_activity_playground.explorer.video import explorer_video_main
from geo_activity_playground.heatmap import generate_heatmaps_per_cluster
from geo_activity_playground.importers.directory import import_from_directory
from geo_activity_playground.importers.strava_api import import_from_strava_api
from geo_activity_playground.webui.app import webui_main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilities to work with recorded activities."
    )
    parser.set_defaults(func=lambda options: parser.print_help())
    parser.add_argument("--basedir", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument(
        "--source",
        choices=["strava-api", "strava-export", "directory"],
        default="strava-api",
    )
    parser.add_argument(
        "--loglevel",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
    )

    subparsers = parser.add_subparsers(
        description="The tools are organized in subcommands.", metavar="Command"
    )

    subparser = subparsers.add_parser(
        "explorer",
        help="Generate GeoJSON/GPX files with explored and missing explorer tiles.",
    )
    subparser.set_defaults(
        func=lambda options: main_explorer(
            make_time_series_source(options.basedir, options.source)
        )
    )

    subparser = subparsers.add_parser(
        "explorer-video", help="Generate video with explorer timeline."
    )
    subparser.set_defaults(func=lambda options: explorer_video_main())

    # subparser = subparsers.add_parser(
    #     "heatmaps", help="Generate heatmaps from activities"
    # )
    # subparser.set_defaults(
    #     func=lambda options: generate_heatmaps_per_cluster(
    #         make_time_series_source(options.basedir, options.source)
    #     )
    # )

    subparser = subparsers.add_parser("serve", help="Launch webserver")
    subparser.set_defaults(
        func=lambda options: webui_main(
            options.basedir, make_activity_repository(options.basedir, options.source)
        )
    )

    subparser = subparsers.add_parser("cache", help="Cache stuff")
    subparser.set_defaults(
        func=lambda options: make_activity_repository(options.basedir, options.source)
    )

    options = parser.parse_args()
    coloredlogs.install(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=options.loglevel.upper(),
    )
    options.func(options)


def main_explorer(ts_source: TimeSeriesSource) -> None:
    points = get_border_tiles(ts_source)
    make_grid_file_geojson(points, "missing_tiles")
    make_grid_file_gpx(points, "missing_tiles")

    points = get_explored_tiles(ts_source)
    make_grid_file_geojson(points, "explored")
    make_grid_file_gpx(points, "explored")


def make_activity_repository(basedir: pathlib.Path, source: str) -> ActivityRepository:
    os.chdir(basedir)
    if source == "strava-api":
        import_from_strava_api()
    elif source == "directory":
        import_from_directory()
    return ActivityRepository()
