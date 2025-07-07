import logging

import sqlalchemy
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import Response
from flask import url_for

from ...core.config import Config
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.enrichment import enrichment_set_timezone
from ...core.enrichment import update_and_commit
from ...explorer.tile_visits import TileVisitAccessor
from ..authenticator import Authenticator
from ..authenticator import needs_authentication

logger = logging.getLogger(__name__)


def make_time_zone_fixer_blueprint(
    authenticator: Authenticator, config: Config, tile_visit_accessor: TileVisitAccessor
) -> Blueprint:

    blueprint = Blueprint("time_zone_fixer", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> str:
        return render_template("time_zone_fixer/index.html.j2")

    @blueprint.route("/local-to-utc")
    @needs_authentication(authenticator)
    def local_to_utc():
        convert(True)
        return redirect(url_for("index"))

    @blueprint.route("/utc-to-utc")
    @needs_authentication(authenticator)
    def utc_to_utc():
        convert(False)
        return redirect(url_for("index"))

    def convert(from_iana: bool) -> None:
        for activity in DB.session.scalars(sqlalchemy.select(Activity)).all():
            if activity.start is None:
                continue

            logger.info(f"Changing time zone for {activity.name} …")

            time_series = activity.raw_time_series
            enrichment_set_timezone(activity, time_series, config)
            if time_series["time"].dt.tz is None:
                time_series["time"] = time_series["time"].dt.tz_localize(
                    activity.iana_timezone if from_iana else "UTC"
                )
            time_series["time"] = time_series["time"].dt.tz_convert("UTC")
            update_and_commit(activity, time_series, config)

    @blueprint.route("/truncate-activities")
    @needs_authentication(authenticator)
    def truncate_activities():
        DB.session.query(Activity).delete()
        DB.session.commit()
        tile_visit_accessor.reset()
        tile_visit_accessor.save()
        return redirect(url_for("upload.reload"))

    return blueprint
