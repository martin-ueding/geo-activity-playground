import argparse
import os
import pathlib

from .explorer.grid_file import get_border_tiles
from .explorer.grid_file import get_explored_tiles
from .explorer.grid_file import make_grid_file_geojson
from .explorer.grid_file import make_grid_file_gpx
from .explorer.video import explorer_video_main
from .heatmap import generate_heatmaps_per_cluster
from geo_activity_playground.core.sources import TimeSeriesSource
from geo_activity_playground.strava.api_access import StravaAPITimeSeriesSource
from geo_activity_playground.strava.importing import StravaExportTimeSeriesSource


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilities to work with recorded activities."
    )
    parser.set_defaults(func=lambda options: parser.print_help())
    parser.add_argument("--basedir", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--source", choices=["api", "export"], default="api")

    subparsers = parser.add_subparsers(
        description="The tools are organized in subcommands.", metavar="Command"
    )

    subparser = subparsers.add_parser(
        "explorer-missing", help="Generate GPX file with missing explorer tiles."
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

    subparser = subparsers.add_parser(
        "heatmaps", help="Generate heatmaps from activities"
    )
    subparser.set_defaults(
        func=lambda options: generate_heatmaps_per_cluster(
            make_time_series_source(options.basedir, options.source)
        )
    )

    options = parser.parse_args()
    options.func(options)


def main_explorer(ts_source: TimeSeriesSource) -> None:
    points = get_border_tiles(ts_source)
    make_grid_file_geojson(points, "missing_tiles")
    make_grid_file_gpx(points, "missing_tiles")

    points = get_explored_tiles(ts_source)
    make_grid_file_geojson(points, "explored")
    make_grid_file_gpx(points, "explored")


def make_time_series_source(basedir: pathlib.Path, source: str) -> TimeSeriesSource:
    os.chdir(basedir)

    ts_source: TimeSeriesSource
    if source == "api":
        ts_source = StravaAPITimeSeriesSource()
    elif source == "export":
        ts_source = StravaExportTimeSeriesSource()
    return ts_source
