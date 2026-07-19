import altair as alt
import pandas as pd
from flask_babel import gettext as _

from .model import Segment


def segment_df(segment: Segment) -> pd.DataFrame:
    columns = [
        "distance_km",
        "duration_s",
        "duration",
        "direction",
        "average_speed_kmh",
        "power_avg",
        "entry_time",
        "exit_time",
        "activity_id",
        "activity_name",
        "equipment_name",
        "kind_name",
    ]
    rows = []
    for match in segment.matches:
        duration_s = abs(match.duration.total_seconds())
        if duration_s > 0:
            average_speed_kmh = abs(match.distance_km) / (duration_s / 3600)
        else:
            average_speed_kmh = None
        rows.append(
            {
                "distance_km": abs(match.distance_km),
                "duration_s": duration_s,
                "duration": abs(match.duration),
                "direction": (
                    "Forward" if match.duration.total_seconds() > 0 else "Backward"
                ),
                "average_speed_kmh": average_speed_kmh,
                "power_avg": match.power_avg,
                "entry_time": match.entry_time,
                "exit_time": match.exit_time,
                "activity_id": match.activity.id,
                "activity_name": match.activity.name,
                "equipment_name": (
                    match.activity.equipment.name
                    if match.activity.equipment is not None
                    else ""
                ),
                "kind_name": (
                    match.activity.kind.name if match.activity.kind is not None else ""
                ),
            }
        )
    return pd.DataFrame.from_records(rows, columns=columns).sort_values(
        "entry_time", ascending=False
    )


def make_plots(df: pd.DataFrame) -> dict[str, str]:
    duration_histogram = (
        alt.Chart(df, width=500)
        .mark_bar()
        .encode(
            alt.X("duration_s", bin=alt.Bin(step=15), title=_("Duration / s")),
            alt.Y("count()"),
            alt.Color("direction", title=_("Direction")),
        )
        .interactive(bind_y=False)
        .to_json(format="vega")
    )

    duration_boxplot = (
        alt.Chart(df, width=500)
        .mark_boxplot()
        .encode(
            alt.Y("direction", title=_("Direction")),
            alt.X("duration_s", title=_("Duration / s")),
            alt.Color("direction", title=_("Direction")),
        )
        .to_json(format="vega")
    )

    return {
        _("Duration Histogram"): duration_histogram,
        _("Duration by Direction"): duration_boxplot,
    }
