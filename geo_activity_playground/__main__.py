import argparse
import pathlib

from .explorer.converters import combine_tile_history
from .explorer.converters import generate_tile_history
from .explorer.grid_file import get_border_tiles
from .explorer.grid_file import make_adapted_grid_file
from .explorer.grid_file import make_grid_file
from geo_activity_playground.explorer.video import explorer_video_main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilities to work with recorded activities."
    )
    parser.set_defaults(func=lambda options: parser.print_help())
    subparsers = parser.add_subparsers(
        description="The tools are organized in subcommands.", metavar="Command"
    )

    explorer_missing = subparsers.add_parser(
        "explorer-missing", help="Generate GPX file with missing explorer tiles."
    )
    explorer_missing.add_argument("path", type=pathlib.Path)
    explorer_missing.set_defaults(func=lambda options: main_explorer(options.path))

    explorer_grid = subparsers.add_parser(
        "explorer-grid", help="Generate GPX file with explorer grid."
    )
    explorer_grid.add_argument("west", type=int)
    explorer_grid.add_argument("north", type=int)
    explorer_grid.add_argument("east", type=int)
    explorer_grid.add_argument("south", type=int)
    explorer_grid.add_argument("path", type=pathlib.Path)
    explorer_grid.set_defaults(
        func=lambda options: make_grid_file(
            options.west, options.north, options.east, options.south, options.path
        )
    )

    explorer_video = subparsers.add_parser(
        "explorer-video", help="Generate video with explorer timeline."
    )
    explorer_video.set_defaults(func=lambda options: explorer_video_main())

    options = parser.parse_args()
    options.func(options)


def main_explorer(path: pathlib.Path) -> None:
    border_x, border_y = get_border_tiles()
    make_adapted_grid_file(border_x, border_y, path)


def main_x() -> None:
    generate_tile_history()
    combine_tile_history()
