import pathlib

import click

from .explorer.grid_file import make_grid_file, get_border_tiles, make_adapted_grid_file
from .explorer.converters import generate_tile_history, combine_tile_history


@click.group()
def main() -> None:
    generate_tile_history()
    combine_tile_history()


@main.command()
@click.option('--west', required=True, type=int)
@click.option('--north', required=True, type=int)
@click.option('--east', required=True, type=int)
@click.option('--south', required=True, type=int)
@click.option('--path', required=True, type=pathlib.Path)
def grid_file(west: int, north: int, east: int, south: int, path: pathlib.Path) -> None:
    make_grid_file(west, north, east, south, path)


@main.command()
@click.option('--path', required=True, type=pathlib.Path)
def adapted_grid_file(path: pathlib.Path) -> None:
    border_x, border_y = get_border_tiles()
    make_adapted_grid_file(border_x, border_y, path)

if __name__ == "__main__":
    main()