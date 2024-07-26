import logging
import os
import pathlib
import sys

from flask import flash
from flask import redirect
from flask import request
from flask import Response
from werkzeug.utils import secure_filename

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import embellish_time_series
from geo_activity_playground.explorer.tile_visits import compute_tile_evolution
from geo_activity_playground.explorer.tile_visits import compute_tile_visits
from geo_activity_playground.explorer.tile_visits import TileVisitAccessor
from geo_activity_playground.importers.directory import get_file_hash
from geo_activity_playground.importers.directory import import_from_directory
from geo_activity_playground.importers.strava_api import import_from_strava_api
from geo_activity_playground.importers.strava_checkout import (
    import_from_strava_checkout,
)


logger = logging.getLogger(__name__)


class UploadController:
    def __init__(
        self,
        repository: ActivityRepository,
        tile_visit_accessor: TileVisitAccessor,
        config: dict,
    ) -> None:
        self._repository = repository
        self._tile_visit_accessor = tile_visit_accessor
        self._config = config

    def render_form(self) -> dict:
        directories = []
        for root, dirs, files in os.walk("Activities"):
            directories.append(root)
        directories.sort()
        return {
            "directories": directories,
            "has_upload": "password" in self._config.get("upload", {}),
        }

    def receive(self) -> Response:
        # check if the post request has the file part
        if "file" not in request.files:
            flash("No file could be found. Did you select a file?", "warning")
            return redirect("/upload")

        if request.form["password"] != self._config["upload"]["password"]:
            flash("Incorrect upload password!", "danger")
            return redirect("/upload")

        file = request.files["file"]
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == "":
            flash("No selected file", "warning")
            return redirect("/upload")
        if file:
            filename = secure_filename(file.filename)
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
            file.save(target_path)
            scan_for_activities(
                self._repository,
                self._tile_visit_accessor,
                self._config,
                skip_strava=True,
            )
            activity_id = get_file_hash(target_path)
            flash(f"Activity was saved with ID {activity_id}.", "success")
            return redirect(f"/activity/{activity_id}")


def scan_for_activities(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: dict,
    skip_strava: bool = False,
) -> None:
    if pathlib.Path("Activities").exists():
        import_from_directory(
            repository,
            config.get("kind", {}),
            config.get("metadata_extraction_regexes", []),
        )
    if pathlib.Path("Strava Export").exists():
        import_from_strava_checkout(repository)
    if "strava" in config and not skip_strava:
        import_from_strava_api(repository)

    if len(repository) == 0:
        logger.error(
            f"No activities found. You need to either add activity files (GPX, FIT, …) to {pathlib.Path('Activities')} or set up the Strava API. Starting without any activities is unfortunately not supported."
        )
        sys.exit(1)

    embellish_time_series(repository)
    compute_tile_visits(repository, tile_visit_accessor)
    compute_tile_evolution(tile_visit_accessor)
