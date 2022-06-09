import click

from .explorer.converters import generate_tile_history, combine_tile_history


@click.command()
def main() -> None:
    generate_tile_history()
    combine_tile_history()


if __name__ == "__main__":
    main()