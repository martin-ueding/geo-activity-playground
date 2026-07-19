import os
import pathlib

import sqlalchemy
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Activity
from ...core.scan import scan_for_activities
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes


def make_upload_blueprint(
    repository: ActivityRepository,
    config_accessor: ConfigAccessor,
    authenticator: Authenticator,
    flasher: Flasher,
) -> Blueprint:
    blueprint = Blueprint("upload", __name__, template_folder="templates")

    @blueprint.route("/")
    @needs_authentication(authenticator)
    def index():
        pathlib.Path("Activities").mkdir(exist_ok=True, parents=True)
        directories = []
        for root, _, _ in os.walk("Activities"):
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
        for file in request.files.getlist("file"):
            filename = file.filename
            assert filename is not None
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
            config_accessor,
            skip_strava=True,
            skip_hammerhead=True,
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
        scan_for_activities(repository, config_accessor)
        flash("Scanned for new activities.", category="success")
        return redirect(url_for("index"))

    return blueprint
