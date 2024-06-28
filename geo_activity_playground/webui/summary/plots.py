df["year"] = [start.year for start in df["start"]]
df["month"] = [start.month for start in df["start"]]
df["day"] = [start.day for start in df["start"]]
df["week"] = [start.isocalendar().week for start in df["start"]]
df["hours"] = [
    elapsed_time.total_seconds() / 3600 for elapsed_time in df["elapsed_time"]
]
del df["elapsed_time"]


year_kind_total = (
    df[["year", "kind", "distance_km", "hours"]]
    .groupby(["year", "kind"])
    .sum()
    .reset_index()
)


(
    alt.Chart(year_kind_total)
    .mark_bar()
    .encode(alt.X("year:O"), alt.Y("distance_km"), alt.Color("kind"))
)


year_cumulative = (
    df[["year", "week", "distance_km"]]
    .groupby("year")
    .apply(
        lambda group: pd.DataFrame(
            {"week": group["week"], "distance_km": group["distance_km"].cumsum()}
        )
    )
    .reset_index()
)
year_cumulative


(
    alt.Chart(year_cumulative)
    .mark_line()
    .encode(
        alt.X("week"), alt.Y("distance_km"), alt.Color("year:N"), alt.Tooltip("year")
    )
)

(
    alt.Chart(df)
    .mark_bar()
    .encode(
        alt.X("distance_km", bin=alt.Bin(step=5)), alt.Y("count()"), alt.Color("kind")
    )
)


year_kind_mean = (
    df[["year", "kind", "distance_km", "hours"]]
    .groupby(["year", "kind"])
    .mean()
    .reset_index()
)

year_kind_mean_distance = year_kind_mean.pivot(
    index="year", columns="kind", values="distance_km"
).reset_index()

week_kind_total_distance = (
    df[["year", "week", "kind", "distance_km"]]
    .groupby(["year", "week", "kind"])
    .sum()
    .reset_index()
)
week_kind_total_distance["year_week"] = [
    f"{year}-{week:02d}"
    for year, week in zip(
        week_kind_total_distance["year"], week_kind_total_distance["week"]
    )
]

import datetime


last_year = week_kind_total_distance["year"].iloc[-1]
last_week = week_kind_total_distance["week"].iloc[-1]

(
    alt.Chart(
        week_kind_total_distance.loc[
            (week_kind_total_distance["year"] == last_year)
            | (week_kind_total_distance["year"] == last_year - 1)
            & (week_kind_total_distance["week"] >= last_week)
        ]
    )
    .mark_bar()
    .encode(alt.X("year_week"), alt.Y("distance_km"), alt.Color("kind"))
)
