import datetime

import sqlalchemy

from ...core.datamodel import DB, Activity


def _lookup_location(
    time: datetime.datetime,
) -> tuple[float, float] | None:
    activity = DB.session.scalar(
        sqlalchemy.select(Activity)
        .where(
            Activity.start.is_not(None),
            Activity.elapsed_time.is_not(None),
            Activity.start <= time,
        )
        .order_by(Activity.start.desc())
        .limit(1)
    )
    if activity is None or activity.start_utc + activity.elapsed_time < time:
        return None

    time_series = activity.time_series
    after = time_series.loc[time_series["time"] >= time]
    if after.empty:
        return None
    row = after.iloc[0]
    return float(row["latitude"]), float(row["longitude"])
