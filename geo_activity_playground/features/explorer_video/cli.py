import argparse
import pathlib

from .video import ExplorerVideoOptions, generate_explorer_video


def main_video_explorer(options) -> None:
    output_path = generate_explorer_video(
        ExplorerVideoOptions(
            basedir=options.basedir,
            zoom=options.zoom,
            width=options.video_width,
            height=options.video_height,
            fps=options.fps,
            output_path=options.output_path,
            steps_per_tile=options.steps_per_tile,
            fade_frames=options.fade_frames,
            pause_frames=options.pause_frames,
            download_workers=options.download_workers,
            map_tile_url=options.map_tile_url,
        )
    )
    print(f"Wrote explorer video to {output_path}")


def register_main_explorer_video(subparsers: argparse._SubParsersAction) -> None:
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
    subparser.set_defaults(func=main_video_explorer)
