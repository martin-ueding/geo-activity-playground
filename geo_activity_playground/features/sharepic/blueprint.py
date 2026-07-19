import datetime

import sqlalchemy
from flask import Blueprint, Response
from flask.typing import ResponseReturnValue

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB, PrivacyZone
from .render import make_day_sharepic, make_sharepic


def make_sharepic_blueprint(
    repository: ActivityRepository, config_accessor: ConfigAccessor
) -> Blueprint:
    blueprint = Blueprint("sharepic", __name__, template_folder="templates")

    @blueprint.route("/activity/<int:id>.png")
    def activity(id: int) -> ResponseReturnValue:
        activity = repository.get_activity_by_id(id)
        time_series = repository.get_time_series(id)
        for privacy_zone in DB.session.scalars(sqlalchemy.select(PrivacyZone)).all():
            time_series = privacy_zone.filter_time_series(time_series)
        if len(time_series) == 0:
            time_series = repository.get_time_series(id)
        return Response(
            make_sharepic(
                activity,
                time_series,
                config_accessor.ui().sharepic_suppressed_fields,
                config_accessor.map(),
            ),
            mimetype="image/png",
        )

    @blueprint.route("/day/<int:year>/<int:month>/<int:day>.png")
    def day(year: int, month: int, day: int) -> ResponseReturnValue:
        config = config_accessor.map()
        meta = repository.meta
        selection = meta["start_local"].dt.date == datetime.date(year, month, day)
        activities_that_day = meta.loc[selection]

        time_series = [
            repository.get_time_series(activity_id)
            for activity_id in activities_that_day["id"]
        ]
        assert len(activities_that_day) > 0
        assert len(time_series) > 0
        return Response(
            make_day_sharepic(activities_that_day, time_series, config),
            mimetype="image/png",
        )

    return blueprint
