import pathlib
import shutil

import dateutil.parser
import numpy as np
import pandas as pd
from tqdm import tqdm


def nan_as_none(elem):
    if isinstance(elem, float) and np.isnan(elem):
        return None
    else:
        return elem


def convert_strava_checkout(
    checkout_path: pathlib.Path, playground_path: pathlib.Path
) -> None:
    activities = pd.read_csv(checkout_path / "activities.csv")
    print(activities)

    for _, row in tqdm(activities.iterrows(), desc="Import activity files"):
        activity_date = dateutil.parser.parse(row["Activity Date"])
        activity_name = row["Activity Name"]
        activity_kind = row["Activity Type"]
        is_commute = row["Commute"] == "true"
        equipment = (
            nan_as_none(row["Activity Gear"])
            or nan_as_none(row["Bike"])
            or nan_as_none(row["Gear"])
            or ""
        )
        activity_file = checkout_path / row["Filename"]

        activity_target = playground_path / "Activities" / str(activity_kind)
        if equipment:
            activity_target /= str(equipment)
        if is_commute:
            activity_target /= "Commute"

        activity_target /= "".join(
            [
                f"{activity_date.year:04d}-{activity_date.month:02d}-{activity_date.day:02d}",
                " ",
                f"{activity_date.hour:02d}-{activity_date.minute:02d}-{activity_date.second:02d}",
                " ",
                activity_name,
            ]
            + activity_file.suffixes
        )

        activity_target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy(activity_file, activity_target)
