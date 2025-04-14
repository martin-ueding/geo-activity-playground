import collections
import datetime

from flask import Blueprint
from flask import render_template

from ...core.activities import ActivityRepository


def make_calendar_blueprint(repository: ActivityRepository) -> Blueprint:
    blueprint = Blueprint("calendar", __name__, template_folder="templates")

    @blueprint.route("/")
    def index():
        meta = repository.meta

        monthly_distance = meta.groupby(
            ["year", "month"],
        ).apply(lambda group: sum(group["distance_km"]), include_groups=False)
        monthly_distance.name = "total_distance_km"
        monthly_pivot = (
            monthly_distance.reset_index()
            .pivot(index="month", columns="year", values="total_distance_km")
            .fillna(0.0)
        )

        yearly_distance = meta.groupby(["year"]).apply(
            lambda group: sum(group["distance_km"]), include_groups=False
        )
        yearly_distance.name = "total_distance_km"
        yearly_distances = {
            row["year"]: row["total_distance_km"]
            for index, row in yearly_distance.reset_index().iterrows()
        }

        context = {
            "num_activities": len(repository),
            "monthly_distances": monthly_pivot,
            "yearly_distances": yearly_distances,
        }
        return render_template("calendar/index.html.j2", **context)

    @blueprint.route("/<int:year>/<int:month>")
    def month(year: int, month: int):
        meta = repository.meta

        filtered = meta.loc[
            (meta["year"] == year) & (meta["month"] == month)
        ].sort_values("start")

        weeks = collections.defaultdict(dict)
        day_of_month = collections.defaultdict(dict)
        date = datetime.datetime(year, month, 1)
        while date.month == month:
            iso = date.isocalendar()
            weeks[iso.week][iso.weekday] = []
            day_of_month[iso.week][iso.weekday] = date.day
            date += datetime.timedelta(days=1)

        for index, row in filtered.iterrows():
            iso = row["start"].isocalendar()
            weeks[iso.week][iso.weekday].append(
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "distance_km": row["distance_km"],
                    "id": row["id"],
                }
            )

        context = {
            "year": year,
            "month": month,
            "weeks": weeks,
            "day_of_month": day_of_month,
        }

        return render_template("calendar/month.html.j2", **context)

    return blueprint
