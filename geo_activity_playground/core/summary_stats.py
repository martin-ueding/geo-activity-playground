import pandas as pd


def get_equipment_use_table(activity_meta: pd.DataFrame) -> pd.DataFrame:
    result = (
        activity_meta.groupby("equipment")
        .apply(
            lambda group: pd.Series(
                {
                    "total_distance_km": int(group["distance_km"].sum().round()),
                    "first_use": group["start"].min(skipna=True),
                    "last_use": group["start"].max(skipna=True),
                },
            ),
            include_groups=False,
        )
        .sort_values("last_use", ascending=False)
    )
    result["first_use"] = [date.date().isoformat() for date in result["first_use"]]
    result["last_use"] = [date.date().isoformat() for date in result["last_use"]]
    return result.reset_index().to_dict(orient="records")
