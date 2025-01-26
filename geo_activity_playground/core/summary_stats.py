import pandas as pd


def get_equipment_use_table(
    activity_meta: pd.DataFrame, offsets: dict[str, float]
) -> pd.DataFrame:
    result = (
        activity_meta.groupby("equipment")
        .apply(
            lambda group: pd.Series(
                {
                    "total_distance_km": group["distance_km"].sum(),
                    "first_use": group["start"].min(skipna=True),
                    "last_use": group["start"].max(skipna=True),
                },
            ),
            include_groups=False,
        )
        .sort_values("last_use", ascending=False)
    )
    for equipment, offset in offsets.items():
        result.loc[equipment, "total_distance_km"] += offset

    result["total_distance_km"] = [
        int(round(elem)) for elem in result["total_distance_km"]
    ]
    result["first_use"] = [date.date().isoformat() for date in result["first_use"]]
    result["last_use"] = [date.date().isoformat() for date in result["last_use"]]

    return result.reset_index()
