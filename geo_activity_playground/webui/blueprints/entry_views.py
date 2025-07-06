import collections
import datetime
from typing import Any

import altair as alt
import flask
import pandas as pd
import sqlalchemy
from flask import render_template
from flask import Response
from flask.typing import ResponseReturnValue

from ...core.activities import ActivityRepository
from ...core.activities import make_geojson_from_time_series
from ...core.config import Config
from ...core.datamodel import Activity
from ...core.datamodel import DB
from ..columns import column_distance
from ..columns import column_elevation_gain
from ..columns import ColumnDescription
from ..columns import META_COLUMNS
from ..plot_util import make_kind_scale


def register_entry_views(
    app: flask.Flask, repository: ActivityRepository, config: Config
) -> None:
    @app.route("/")
    def index() -> ResponseReturnValue:
        context: dict[str, Any] = {"latest_activities": []}
        df = repository.meta

        if len(repository):
            kind_scale = make_kind_scale(df, config)
            context["last_30_days_plot"] = {
                column.display_name: _last_30_days_meta_plot(df, kind_scale, column)
                for column in META_COLUMNS
            }

            context["latest_activities"] = collections.defaultdict(list)
            for activity in DB.session.scalars(
                sqlalchemy.select(Activity)
                .where(Activity.start.is_not(None))
                .order_by(Activity.start.desc())
                .limit(100)
            ):
                context["latest_activities"][activity.start_local_tz.date()].append(
                    {
                        "activity": activity,
                        "line_geojson": make_geojson_from_time_series(
                            activity.time_series
                        ),
                    }
                )

        return render_template("home.html.j2", **context)


def _last_30_days_meta_plot(
    meta: pd.DataFrame, kind_scale: alt.Scale, column: ColumnDescription
) -> str:
    before_30_days = pd.to_datetime(
        datetime.datetime.now() - datetime.timedelta(days=31)
    )
    return (
        alt.Chart(
            meta.loc[meta["start"] > before_30_days],
            width=700,
            height=200,
            title=f"{column.display_name} per day",
        )
        .mark_bar()
        .encode(
            alt.X("yearmonthdate(start)", title="Date"),
            alt.Y(f"sum({column.name})", title=f"{column.name} / {column.unit}"),
            alt.Color("kind", scale=kind_scale, title="Kind"),
            [
                alt.Tooltip("yearmonthdate(start)", title="Date"),
                alt.Tooltip("kind", title="Kind"),
                alt.Tooltip(
                    f"sum({column.name})",
                    format=column.format,
                    title=f"{column.display_name} / {column.unit}",
                ),
            ],
        )
        .to_json(format="vega")
    )
