import os
import pathlib

import sqlalchemy
from flask import Blueprint
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from ...core.activities import ActivityRepository
from ...core.config import Config
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...explorer.tile_visits import compute_tile_evolution
from ...explorer.tile_visits import compute_tile_visits_new
from ...explorer.tile_visits import TileVisitAccessor
from ...importers.directory import import_from_directory
from ...importers.strava_api import import_from_strava_api
from ...importers.strava_checkout import import_from_strava_checkout
from ..authenticator import Authenticator
from ..authenticator import needs_authentication
from ..flasher import Flasher
from ..flasher import FlashTypes


def make_upload_blueprint(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    authenticator: Authenticator,
    flasher: Flasher,
) -> Blueprint:
    blueprint = Blueprint("upload", __name__, template_folder="templates")

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        pathlib.Path("Activities").mkdir(exist_ok=True, parents=True)
        directories = []
        for root, dirs, files in os.walk("Activities"):
            directories.append(root)
        directories.sort()
        return render_template("upload/index.html.j2", directories=directories)

    @blueprint.route("/receive", methods=["POST"])
    @needs_authentication(authenticator)
    def receive():
        # check if the post request has the file part
        if "file" not in request.files:
            flash("No file could be found. Did you select a file?", "warning")
            return redirect("/upload")

        file = request.files["file"]
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == "":
            flash("No selected file", "warning")
            return redirect("/upload")
        if file:
            filename = file.filename
            target_path = pathlib.Path(request.form["directory"]) / filename
            assert target_path.suffix in [
                ".csv",
                ".fit",
                ".gpx",
                ".gz",
                ".kml",
                ".kmz",
                ".tcx",
            ]
            assert target_path.is_relative_to("Activities")
            if target_path.exists():
                flasher.flash_message(
                    f"An activity with path '{target_path}' already exists. Rename the file and try again.",
                    FlashTypes.DANGER,
                )
                return redirect(url_for(".index"))
            file.save(target_path)
            scan_for_activities(
                repository,
                tile_visit_accessor,
                config,
                skip_strava=True,
            )
            latest_activity = DB.session.scalar(
                sqlalchemy.select(Activity).order_by(Activity.id.desc()).limit(1)
            )
            assert latest_activity is not None
            flash(f"Activity was saved with ID {latest_activity.id}.", "success")
            return redirect(f"/activity/{latest_activity.id}")

    @blueprint.route("/refresh")
    @needs_authentication(authenticator)
    def reload():
        return render_template("upload/reload.html.j2")

    @blueprint.route("/execute-reload")
    @needs_authentication(authenticator)
    def execute_reload():
        scan_for_activities(
            repository,
            tile_visit_accessor,
            config,
            skip_strava=True,
        )
        flash("Scanned for new activities.", category="success")
        return redirect(url_for("index"))

    return blueprint


def scan_for_activities(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    skip_strava: bool = False,
) -> None:
    if pathlib.Path("Activities").exists():
        import_from_directory(repository, tile_visit_accessor, config)
    if pathlib.Path("Strava Export").exists():
        import_from_strava_checkout(config)
    if config.strava_client_code and not skip_strava:
        import_from_strava_api(config, repository, tile_visit_accessor)

    if len(repository) > 0:
        compute_tile_visits_new(repository, tile_visit_accessor)
        compute_tile_evolution(tile_visit_accessor.tile_state, config)
        tile_visit_accessor.save()
