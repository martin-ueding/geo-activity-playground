import logging
import pathlib

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...webui.authenticator import Authenticator, needs_authentication
from .video import ExplorerVideoOptions, generate_explorer_video

logger = logging.getLogger(__name__)


def make_explorer_video_blueprint(
    authenticator: Authenticator, config_accessor: ConfigAccessor
) -> Blueprint:
    blueprint = Blueprint("explorer_video", __name__, template_folder="templates")

    @blueprint.route("/video")
    @needs_authentication(authenticator)
    def video() -> ResponseReturnValue:
        zoom_levels = sorted(set(config_accessor.ui().explorer_zoom_levels))
        selected_zoom = request.args.get("zoom", type=int)
        if selected_zoom not in zoom_levels:
            selected_zoom = zoom_levels[0] if zoom_levels else 14
        return render_template(
            "explorer_video/video.html.j2",
            zoom_levels=zoom_levels,
            selected_zoom=selected_zoom,
        )

    @blueprint.post("/video")
    @needs_authentication(authenticator)
    def generate_video() -> ResponseReturnValue:
        zoom = request.form.get("zoom", type=int, default=14)
        if zoom not in config_accessor.ui().explorer_zoom_levels:
            flash(_("The selected zoom level is not enabled."), category="danger")
            return redirect(url_for(".video"))
        video_width = request.form.get("video_width", type=int, default=1920)
        video_height = request.form.get("video_height", type=int, default=1080)
        fps = request.form.get("fps", type=int, default=30)
        steps_per_tile = request.form.get("steps_per_tile", type=int, default=12)
        fade_frames = request.form.get("fade_frames", type=int, default=12)
        download_workers = request.form.get("download_workers", type=int, default=16)

        if video_width <= 0 or video_height <= 0 or fps <= 0:
            flash(_("Width, height and FPS must be positive."), category="danger")
            return redirect(url_for(".video", zoom=zoom))
        if steps_per_tile <= 0 or fade_frames < 0:
            flash(
                _(
                    "Steps per tile must be positive and fade frames must be non-negative."
                ),
                category="danger",
            )
            return redirect(url_for(".video", zoom=zoom))
        if download_workers <= 0:
            flash(_("Download workers must be positive."), category="danger")
            return redirect(url_for(".video", zoom=zoom))

        try:
            output_path = generate_explorer_video(
                ExplorerVideoOptions(
                    basedir=pathlib.Path.cwd(),
                    zoom=zoom,
                    width=video_width,
                    height=video_height,
                    fps=fps,
                    steps_per_tile=steps_per_tile,
                    fade_frames=fade_frames,
                    download_workers=download_workers,
                )
            )
        except Exception as exc:
            logger.exception("Failed to generate explorer video")
            flash(
                _("Could not generate explorer video: %(error)s", error=str(exc)),
                category="danger",
            )
        else:
            flash(
                _("Explorer video written to %(path)s", path=str(output_path)),
                category="success",
            )
        return redirect(url_for(".video", zoom=zoom))

    return blueprint
