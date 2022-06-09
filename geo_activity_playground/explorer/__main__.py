import pathlib

import click

from .grid_file import make_grid_file


@click.command()
@click.option('--west', required=True, type=int)
@click.option('--north', required=True, type=int)
@click.option('--east', required=True, type=int)
@click.option('--south', required=True, type=int)
@click.option('--path', required=True, type=pathlib.Path)
def main(west: int, north: int, east: int, south: int, path: pathlib.Path) -> None:
    make_grid_file(west, north, east, south, path)


if __name__ == "__main__":
    main()