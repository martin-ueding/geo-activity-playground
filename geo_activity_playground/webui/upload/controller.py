import logging
import os
import pathlib

import sqlalchemy.orm
from flask import flash
from flask import redirect
from flask import request
from flask import Response
from flask import url_for
from werkzeug.utils import secure_filename

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activities import build_activity_meta
from geo_activity_playground.core.activities import build_activity_meta_sql
from geo_activity_playground.core.config import Config
from geo_activity_playground.core.enrichment import enrich_activities
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
        config: Config,
        db_session: sqlalchemy.orm.Session,
    ) -> None:
        self._repository = repository
        self._tile_visit_accessor = tile_visit_accessor
        self._config = config
        self._db_session = db_session

    def render_form(self) -> dict:
        directories = []
        for root, dirs, files in os.walk("Activities"):
            directories.append(root)
        directories.sort()
        return {
            "directories": directories,
            "has_upload": self._config.upload_password,
        }

    def receive(self) -> Response:
        # check if the post request has the file part
        if "file" not in request.files:
            flash("No file could be found. Did you select a file?", "warning")
            return redirect("/upload")

        if request.form["password"] != self._config.upload_password:
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
                self._db_session,
                skip_strava=True,
            )
            activity_id = get_file_hash(target_path)
            flash(f"Activity was saved with ID {activity_id}.", "success")
            return redirect(f"/activity/{activity_id}")

    def execute_reload(self) -> None:
        scan_for_activities(
            self._repository,
            self._tile_visit_accessor,
            self._config,
            self._db_session,
            skip_strava=True,
        )
        flash("Scanned for new activities.", category="success")
        return redirect(url_for("index"))


def scan_for_activities(
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
    config: Config,
    db_session: sqlalchemy.orm.Session,
    skip_strava: bool = False,
) -> None:
    if pathlib.Path("Activities").exists():
        import_from_directory(
            config.metadata_extraction_regexes,
            config.num_processes,
        )
    if pathlib.Path("Strava Export").exists():
        import_from_strava_checkout()
    if config.strava_client_code and not skip_strava:
        import_from_strava_api(config)

    enrich_activities(config)
    build_activity_meta_sql(db_session)
    build_activity_meta()
    repository.reload()

    if len(repository) > 0:
        compute_tile_visits(repository, tile_visit_accessor)
        compute_tile_evolution(tile_visit_accessor, config)
