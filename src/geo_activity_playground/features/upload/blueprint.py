import os
import pathlib
import uuid

import sqlalchemy
from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Activity
from ...core.scan import scan_for_activities
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from ..directory_import.importer import file_sha256


def _content_suffix(path: pathlib.Path) -> str:
    """The suffix that determines the parser, `.fit.gz` included."""
    if path.suffix == ".gz":
        return "".join(path.suffixes[-2:])
    return path.suffix


def _store_under_content_hash(file, target_path: pathlib.Path) -> pathlib.Path | None:
    """Store an upload whose name is taken as `<sha256><suffix>`.

    Returns `None` if a file with that content is already present, which is the
    case when the same file gets uploaded twice.
    """
    temporary_path = target_path.with_name(f".upload-{uuid.uuid4()}")
    file.save(temporary_path)
    content_hash = file_sha256(temporary_path)
    hashed_path = target_path.with_name(content_hash + _content_suffix(target_path))
    if hashed_path.exists() or file_sha256(target_path) == content_hash:
        temporary_path.unlink()
        return None
    temporary_path.rename(hashed_path)
    return hashed_path


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
        directories = sorted(root for root, _dirs, _files in os.walk("Activities"))
        return render_template("upload/index.html.j2", directories=directories)

    @blueprint.route("/receive", methods=["POST"])
    @needs_authentication(authenticator)
    def receive():
        # check if the post request has the file part
        if "file" not in request.files:
            flasher.flash_message(
                _("No file could be found. Did you select a file?"), FlashTypes.WARNING
            )
            return redirect(url_for(".index"))

        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if request.files["file"].filename == "":
            flasher.flash_message(_("No selected file."), FlashTypes.WARNING)
            return redirect(url_for(".index"))

        saved_paths = []
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
                target_path = _store_under_content_hash(file, target_path)
                if target_path is None:
                    flasher.flash_message(
                        _("Skipped '%(filename)s' because that file is already there.")
                        % {"filename": filename},
                        FlashTypes.INFO,
                    )
                    continue
                flasher.flash_message(
                    _(
                        "Stored '%(filename)s' as '%(target_path)s' because that name was taken."
                    )
                    % {"filename": filename, "target_path": target_path},
                    FlashTypes.INFO,
                )
            else:
                file.save(target_path)
            saved_paths.append(str(target_path))

        scan_for_activities(
            repository,
            config_accessor,
            skip_strava=True,
            skip_hammerhead=True,
        )

        activity_ids = DB.session.scalars(
            sqlalchemy.select(Activity.id)
            .filter(Activity.path.in_(saved_paths))
            .order_by(Activity.start)
        ).all()

        if not activity_ids:
            flasher.flash_message(
                _("None of the uploaded files could be imported."), FlashTypes.DANGER
            )
            return redirect(url_for(".index"))

        if len(activity_ids) < len(saved_paths):
            flasher.flash_message(
                _("%(count)s of the uploaded files could not be imported.")
                % {"count": len(saved_paths) - len(activity_ids)},
                FlashTypes.WARNING,
            )

        return redirect(url_for("activity.bulk_edit", id=activity_ids))

    @blueprint.route("/refresh")
    @needs_authentication(authenticator)
    def reload():
        return render_template("upload/reload.html.j2")

    @blueprint.route("/execute-reload")
    @needs_authentication(authenticator)
    def execute_reload():
        scan_for_activities(repository, config_accessor)
        flasher.flash_message(_("Scanned for new activities."), FlashTypes.SUCCESS)
        return redirect(url_for("index"))

    return blueprint
