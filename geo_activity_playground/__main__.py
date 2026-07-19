import argparse
import logging
import pathlib
import sys

import coloredlogs

from .features.activity_photos.cli import (
    register_main_annotate_photos,
    register_main_inspect_photo,
)
from .features.explorer_video.cli import (
    register_main_explorer_video,
)
from .features.heatmap_video.cli import register_main_heatmap_video
from .features.strava_checkout.importer import convert_strava_checkout
from .webui.app import create_app, web_ui_main

logger = logging.getLogger(__name__)


def main_export_kml(options: argparse.Namespace) -> None:
    import os

    from .core.coordinates import Bounds
    from .core.tiles import compute_tile
    from .explorer.grid_file import (
        get_border_tiles,
        make_grid_file_kml,
        make_grid_file_kml_squadrats,
        make_grid_points,
    )
    from .explorer.tile_visits import get_explorer_square, get_tile_history_df

    os.chdir(options.basedir)
    database_path = pathlib.Path("database.sqlite")
    app = create_app(
        database_uri=f"sqlite:///{database_path.absolute()}",
        run_migrations=False,
    )

    with app.app_context():
        if options.export_type == "squadrats":
            explored: dict[int, list[tuple[int, int]]] = {}
            squares: dict[int, tuple[int, int, int]] = {}
            for zoom in (14, 17):
                tiles = get_tile_history_df(zoom)
                if len(tiles):
                    explored[zoom] = list(zip(tiles["tile_x"], tiles["tile_y"]))
                square_x, square_y, square_size = get_explorer_square(zoom)
                if square_x is not None and square_size:
                    squares[zoom] = (square_x, square_y, square_size)
            if not explored:
                logger.error("No explored tiles found.")
                sys.exit(1)
            kml = make_grid_file_kml_squadrats(explored, squares)
        else:
            zoom = options.zoom
            tiles = get_tile_history_df(zoom)
            if tiles.empty:
                logger.error(f"No explored tiles at zoom {zoom}.")
                sys.exit(1)
            if options.export_type == "missing":
                if options.bounds:
                    north, east, south, west = options.bounds
                    x1, y1 = compute_tile(north, west, zoom)
                    x2, y2 = compute_tile(south, east, zoom)
                    tile_bounds = Bounds(x1, y1, x2 + 2, y2 + 2)
                else:
                    margin = options.margin
                    tile_bounds = Bounds(
                        int(tiles["tile_x"].min()) - margin,
                        int(tiles["tile_y"].min()) - margin,
                        int(tiles["tile_x"].max()) + margin + 1,
                        int(tiles["tile_y"].max()) + margin + 1,
                    )
                points = get_border_tiles(tiles, zoom, tile_bounds)
            else:
                points = make_grid_points(zip(tiles["tile_x"], tiles["tile_y"]), zoom)
            kml = make_grid_file_kml(points)

    output: pathlib.Path = options.output
    output.write_text(kml, encoding="utf-8")
    logger.info(f"Written KML to {output}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilities to work with recorded activities."
    )
    parser.set_defaults(func=lambda _options: parser.print_help())
    parser.add_argument(
        "--basedir",
        type=pathlib.Path,
        default=pathlib.Path.cwd(),
        help="Base directory for data and configuration (default: %(default)s)",
    )
    parser.add_argument(
        "--loglevel",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Log verbosity level (default: %(default)s)",
    )

    subparsers = parser.add_subparsers(
        description="The tools are organized in subcommands.", metavar="Command"
    )

    register_main_inspect_photo(subparsers)
    register_main_annotate_photos(subparsers)
    register_main_heatmap_video(subparsers)
    register_main_explorer_video(subparsers)

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
            options.basedir,
            options.skip_reload,
            host=options.host,
            port=options.port,
            strava_begin=options.strava_begin,
            strava_end=options.strava_end,
            hammerhead_begin=options.hammerhead_begin,
            hammerhead_end=options.hammerhead_end,
            http_server=options.http_server,
            threads=options.threads,
            workers=options.workers,
        )
    )
    subparser.add_argument(
        "--host",
        default="127.0.0.1",
        help="IP address to listen on (default: %(default)s)",
    )
    subparser.add_argument(
        "--port",
        default=5000,
        type=int,
        help="Port to listen on (default: %(default)s)",
    )
    subparser.add_argument(
        "--http-server",
        choices=(
            ["waitress", "werkzeug"]
            if sys.platform == "win32"
            else ["waitress", "werkzeug", "gunicorn"]
        ),
        default="waitress" if sys.platform == "win32" else "gunicorn",
        help="HTTP server implementation to use (default: %(default)s)",
    )
    subparser.add_argument(
        "--threads",
        type=int,
        default=8,
        help="Number of threads per server process (default: %(default)s)",
    )
    subparser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker processes (Gunicorn only, default: %(default)s)",
    )
    subparser.add_argument("--skip-reload", action=argparse.BooleanOptionalAction)
    subparser.add_argument(
        "--strava-begin", help="Start date to limit Strava sync, format YYYY-MM-DD"
    )
    subparser.add_argument(
        "--strava-end", help="End date to limit Strava sync, format YYYY-MM-DD"
    )
    subparser.add_argument(
        "--hammerhead-begin",
        help="Start date to limit Hammerhead sync, format YYYY-MM-DD",
    )
    subparser.add_argument(
        "--hammerhead-end",
        help="End date to limit Hammerhead sync, format YYYY-MM-DD",
    )

    subparser = subparsers.add_parser(
        "export-kml",
        help="Export explorer tiles to a KML file",
    )
    subparser.add_argument(
        "--output",
        type=pathlib.Path,
        required=True,
        help="Output KML file path",
    )
    subparser.add_argument(
        "--type",
        dest="export_type",
        choices=["squadrats", "missing", "explored"],
        default="squadrats",
        help=(
            "Type of export: 'squadrats' (Garmin/Squadrats-compatible, zoom 14+17),"
            " 'missing' (unvisited tiles in bounding box), 'explored' (visited tiles)."
            " Default: %(default)s"
        ),
    )
    subparser.add_argument(
        "--zoom",
        type=int,
        default=14,
        help="Zoom level for 'missing' and 'explored' types (default: %(default)s)",
    )
    subparser.add_argument(
        "--margin",
        type=int,
        default=3,
        help=(
            "Tile margin around explored area for 'missing' type"
            " when no --bounds are given (default: %(default)s)"
        ),
    )
    subparser.add_argument(
        "--bounds",
        type=float,
        nargs=4,
        metavar=("NORTH", "EAST", "SOUTH", "WEST"),
        help="Lat/lon bounding box for 'missing' and 'explored' types",
    )
    subparser.set_defaults(func=main_export_kml)

    options = parser.parse_args()
    coloredlogs.install(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=options.loglevel.upper(),
    )

    logging.getLogger("stravalib.protocol.ApiV3").setLevel(logging.WARNING)

    options.func(options)


if __name__ == "__main__":
    main()
