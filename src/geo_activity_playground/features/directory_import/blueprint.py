import logging
import pathlib
import re

import sqlalchemy
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...core.datamodel import (
    DB,
    Activity,
    ActivityImportConfig,
    get_or_make_equipment,
    get_or_make_kind,
)
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from .importer import get_metadata_from_path

logger = logging.getLogger(__name__)


def _apply_metadata_extraction_to_existing(config: ActivityImportConfig) -> int:
    activities = DB.session.scalars(
        sqlalchemy.select(Activity).filter(Activity.path.is_not(sqlalchemy.null()))
    ).all()
    changed = 0
    for activity in activities:
        assert activity.path is not None
        meta = get_metadata_from_path(
            pathlib.Path(activity.path), config.metadata_extraction_regexes
        )
        if not meta:
            continue
        if "name" in meta:
            activity.name = meta["name"]
        if "kind" in meta:
            activity.kind = get_or_make_kind(meta["kind"])
        if "equipment" in meta:
            activity.equipment = get_or_make_equipment(meta["equipment"], config)
        changed += 1
    DB.session.commit()
    return changed


def register_directory_import_settings(
    blueprint: Blueprint,
    authenticator: Authenticator,
    flasher: Flasher,
    config_accessor: ConfigAccessor,
) -> None:
    """Register the directory-import metadata extraction routes onto the settings blueprint."""

    @blueprint.route("/metadata-extraction", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def metadata_extraction():
        if request.method == "POST":
            metadata_extraction_regexes = request.form.getlist("regex")
            new_metadata_extraction_regexes = []
            for regex in metadata_extraction_regexes:
                try:
                    re.compile(regex)
                except re.error as e:
                    flash(
                        f"Cannot parse regex {regex} due to error: {e}",
                        category="danger",
                    )
                else:
                    new_metadata_extraction_regexes.append(regex)

            config_accessor.activity_import().metadata_extraction_regexes = (
                new_metadata_extraction_regexes
            )
            config_accessor.save()
            flash("Updated metadata extraction settings.", category="success")
        context = {
            "metadata_extraction_regexes": config_accessor.activity_import().metadata_extraction_regexes,
        }
        return render_template("settings/metadata-extraction.html.j2", **context)

    @blueprint.route("/metadata-extraction/apply-to-existing", methods=["POST"])
    @needs_authentication(authenticator)
    def metadata_extraction_apply_to_existing():
        changed = _apply_metadata_extraction_to_existing(
            config_accessor.activity_import()
        )
        flasher.flash_message(
            _(
                "Applied metadata extraction regexes to existing activities: %(changed)s updated."
            )
            % {"changed": changed},
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".metadata_extraction"))
