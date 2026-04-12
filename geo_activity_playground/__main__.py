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

    subparser = subparsers.add_parser(
        "explorer-video", help="Generate video with explorer timeline."
    )
    subparser.add_argument(
        "--zoom",
        type=int,
        default=14,
        help="Explorer zoom level (default: %(default)s)",
    )
    subparser.add_argument(
        "--video-width",
        type=int,
        default=1920,
        help="Output video width in pixels (default: %(default)s)",
    )
    subparser.add_argument(
        "--video-height",
        type=int,
        default=1080,
        help="Output video height in pixels (default: %(default)s)",
    )
    subparser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Frames per second for output video (default: %(default)s)",
    )
    subparser.add_argument(
        "--steps-per-tile",
        type=int,
        default=12,
        help="Interpolation frames between consecutive tiles (default: %(default)s)",
    )
    subparser.add_argument(
        "--fade-frames",
        type=int,
        default=12,
        help="Fade-in and fade-out frames per chunk (default: %(default)s)",
    )
    subparser.add_argument(
        "--pause-frames",
        type=int,
        default=12,
        help="Hold frames before fade-out per chunk (default: %(default)s)",
    )
    subparser.add_argument(
        "--download-workers",
        type=int,
        default=16,
        help="Parallel workers for OSM tile downloads (default: %(default)s)",
    )
    subparser.add_argument(
        "--output-path",
        type=pathlib.Path,
        default=None,
        help="Optional output path for MP4 file",
    )
    subparser.add_argument(
        "--map-tile-url",
        default=None,
        help="Optional map tile URL template override",
    )
    subparser.set_defaults(func=explorer_video_main)

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
            http_server=options.http_server,
            waitress_threads=options.waitress_threads,
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
        choices=["waitress", "werkzeug"],
        default="waitress",
        help="HTTP server implementation to use (default: %(default)s)",
    )
    subparser.add_argument(
        "--waitress-threads",
        type=int,
        default=8,
        help="Number of Waitress worker threads (default: %(default)s)",
    )
    subparser.add_argument("--skip-reload", action=argparse.BooleanOptionalAction)
    subparser.add_argument(
        "--strava-begin", help="Start date to limit Strava sync, format YYYY-MM-DD"
    )
    subparser.add_argument(
        "--strava-end", help="End date to limit Strava sync, format YYYY-MM-DD"
    )

    subparser = subparsers.add_parser(
        "heatmap-video", help="Create a video with the evolution of the heatmap"
    )
    subparser.add_argument("latitude", type=float)
    subparser.add_argument("longitude", type=float)
    subparser.add_argument("zoom", type=int)
    subparser.add_argument(
        "--decay",
        type=float,
        default=0.05,
        help="Decay factor per frame (default: %(default)s)",
    )
    subparser.add_argument(
        "--video-width",
        type=int,
        default=1920,
        help="Output video width in pixels (default: %(default)s)",
    )
    subparser.add_argument(
        "--video-height",
        type=int,
        default=1080,
        help="Output video height in pixels (default: %(default)s)",
    )
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
