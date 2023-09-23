import argparse
import os
import pathlib

from .explorer.grid_file import get_border_tiles
from .explorer.grid_file import make_adapted_grid_file
from .explorer.grid_file import make_grid_file
from .explorer.video import explorer_video_main
from .heatmap import heatmaps_main
from .heatmap import heatmaps_main_2
from geo_activity_playground.strava.api_access import sync_from_strava


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilities to work with recorded activities."
    )
    parser.set_defaults(func=lambda options: parser.print_help())
    parser.add_argument("--basedir", type=pathlib.Path, default=pathlib.Path.cwd())
    subparsers = parser.add_subparsers(
        description="The tools are organized in subcommands.", metavar="Command"
    )

    subparser = subparsers.add_parser(
        "explorer-missing", help="Generate GPX file with missing explorer tiles."
    )
    subparser.add_argument("path", type=pathlib.Path)
    subparser.set_defaults(func=lambda options: main_explorer(options.path))

    subparser = subparsers.add_parser(
        "explorer-grid", help="Generate GPX file with explorer grid."
    )
    subparser.add_argument("west", type=int)
    subparser.add_argument("north", type=int)
    subparser.add_argument("east", type=int)
    subparser.add_argument("south", type=int)
    subparser.add_argument("path", type=pathlib.Path)
    subparser.set_defaults(
        func=lambda options: make_grid_file(
            options.west, options.north, options.east, options.south, options.path
        )
    )

    subparser = subparsers.add_parser(
        "explorer-video", help="Generate video with explorer timeline."
    )
    subparser.set_defaults(func=lambda options: explorer_video_main())

    subparser = subparsers.add_parser(
        "heatmaps", help="Generate heatmaps from activities"
    )
    subparser.set_defaults(func=lambda options: heatmaps_main())

    subparser = subparsers.add_parser(
        "heatmaps2", help="Generate heatmaps from activities"
    )
    subparser.set_defaults(func=lambda options: heatmaps_main_2())

    subparser = subparsers.add_parser("magic")
    subparser.set_defaults(func=lambda options: main_magic(options.basedir))

    options = parser.parse_args()
    options.func(options)


def main_explorer(path: pathlib.Path) -> None:
    generate_tile_history()
    combine_tile_history()
    border_x, border_y = get_border_tiles()
    make_adapted_grid_file(border_x, border_y, path)


def main_x() -> None:
    generate_tile_history()
    combine_tile_history()


def main_magic(basedir: pathlib.Path) -> None:
    os.chdir(basedir)
    sync_from_strava()
