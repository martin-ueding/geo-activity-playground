import logging

import sqlalchemy
from flask import Blueprint

from ...core.config import Config
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ...core.enrichment import apply_enrichments
from ...core.enrichment import enrichment_set_timezone

logger = logging.getLogger(__name__)


def make_time_zone_fixer_blueprint(config: Config) -> Blueprint:

    blueprint = Blueprint("time_zone_fixer", __name__, template_folder="templates")

    @blueprint.route("/local-to-utc")
    def local_to_utc() -> str:
        for activity in DB.session.scalars(sqlalchemy.select(Activity)).all():
            if activity.start is None:
                continue

            logger.info(f"Changing time zone for {activity.name} …")

            time_series = activity.raw_time_series
            enrichment_set_timezone(activity, time_series, config)
            if time_series["time"].dt.tz is None:
                time_series["time"] = time_series["time"].dt.tz_localize(
                    activity.iana_timezone
                )
            time_series["time"] = time_series["time"].dt.tz_convert("utc")
            apply_enrichments(activity, time_series, config)
            activity.replace_time_series(time_series)
            DB.session.commit()
        return "Done"

    return blueprint
