import argparse
import logging
import pathlib

import coloredlogs

from .core.photos import main_inspect_photo
from .explorer.video import explorer_video_main
from .heatmap_video import main_heatmap_video
from .importers.strava_checkout import convert_strava_checkout
from .webui.app import web_ui_main

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
            options.basedir,
            options.skip_reload,
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

    subparser = subparsers.add_parser(
        "heatmap-video", help="Create a video with the evolution of the heatmap"
    )
    subparser.add_argument("latitude", type=float)
    subparser.add_argument("longitude", type=float)
    subparser.add_argument("zoom", type=int)
    subparser.add_argument("--decay", type=float, default=0.05)
    subparser.add_argument("--video-width", type=int, default=1920)
    subparser.add_argument("--video-height", type=int, default=1080)
    subparser.set_defaults(func=main_heatmap_video)

    subparser = subparsers.add_parser(
        "inspect-photo",
        help="Extract EXIF data from the image to see how it would be imported",
    )
    subparser.add_argument("path", type=pathlib.Path)
    subparser.set_defaults(func=main_inspect_photo)

    options = parser.parse_args()
    coloredlogs.install(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=options.loglevel.upper(),
    )

    logging.getLogger("stravalib.protocol.ApiV3").setLevel(logging.WARNING)

    options.func(options)


if __name__ == "__main__":
    main()
