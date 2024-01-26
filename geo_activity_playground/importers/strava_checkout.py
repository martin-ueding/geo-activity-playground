import datetime
import logging
import pathlib
import shutil
import traceback

import dateutil.parser
import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.activity_parsers import ActivityParseError
from geo_activity_playground.core.activity_parsers import read_activity
from geo_activity_playground.core.tasks import WorkTracker


logger = logging.getLogger(__name__)


def nan_as_none(elem):
    if isinstance(elem, float) and np.isnan(elem):
        return None
    else:
        return elem


def import_from_strava_checkout(repository: ActivityRepository) -> None:
    checkout_path = pathlib.Path("Strava Export")
    activities = pd.read_csv(checkout_path / "activities.csv")
    activities.index = activities["Activity ID"]
    work_tracker = WorkTracker("import-strava-checkout-activities")
    activities_ids_to_parse = work_tracker.filter(activities["Activity ID"])

    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    activity_stream_dir.mkdir(exist_ok=True, parents=True)

    for activity_id in tqdm(activities_ids_to_parse, desc="Import from Strava export"):
        row = activities.loc[activity_id]
        activity_file = checkout_path / row["Filename"]
        table_activity_meta = {
            "calories": row["Calories"],
            "commute": row["Commute"] == "true",
            "distance": row["Distance"],
            "elapsed_time": datetime.timedelta(seconds=int(row["Elapsed Time"])),
            "equipment": str(
                nan_as_none(row["Activity Gear"])
                or nan_as_none(row["Bike"])
                or nan_as_none(row["Gear"])
                or ""
            ),
            "kind": row["Activity Type"],
            "id": activity_id,
            "name": row["Activity Name"],
            "path": str(activity_file),
            "start": dateutil.parser.parse(row["Activity Date"]).astimezone(
                datetime.timezone.utc
            ),
        }

        time_series_path = activity_stream_dir / f"{activity_id}.parquet"
        if not time_series_path.exists():
            try:
                file_activity_meta, time_series = read_activity(activity_file)
            except ActivityParseError as e:
                logger.error(f"Error while parsing file {activity_file}:")
                traceback.print_exc()
                continue
            except:
                logger.error(
                    f"Encountered a problem with {activity_file=}, see details below."
                )
                raise

            if not len(time_series):
                continue

            time_series.to_parquet(time_series_path)

        work_tracker.mark_done(activity_id)
        repository.add_activity(table_activity_meta)

    repository.commit()
    work_tracker.close()


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
