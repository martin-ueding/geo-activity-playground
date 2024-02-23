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


EXPECTED_COLUMNS = [
    "Activity ID",
    "Activity Date",
    "Activity Name",
    "Activity Type",
    "Activity Description",
    "Elapsed Time",
    "Distance",
    "Max Heart Rate",
    "Relative Effort",
    "Commute",
    "Activity Private Note",
    "Activity Gear",
    "Filename",
    "Athlete Weight",
    "Bike Weight",
    "Elapsed Time.1",
    "Moving Time",
    "Distance.1",
    "Max Speed",
    "Average Speed",
    "Elevation Gain",
    "Elevation Loss",
    "Elevation Low",
    "Elevation High",
    "Max Grade",
    "Average Grade",
    "Average Positive Grade",
    "Average Negative Grade",
    "Max Cadence",
    "Average Cadence",
    "Max Heart Rate.1",
    "Average Heart Rate",
    "Max Watts",
    "Average Watts",
    "Calories",
    "Max Temperature",
    "Average Temperature",
    "Relative Effort.1",
    "Total Work",
    "Number of Runs",
    "Uphill Time",
    "Downhill Time",
    "Other Time",
    "Perceived Exertion",
    "Type",
    "Start Time",
    "Weighted Average Power",
    "Power Count",
    "Prefer Perceived Exertion",
    "Perceived Relative Effort",
    "Commute.1",
    "Total Weight Lifted",
    "From Upload",
    "Grade Adjusted Distance",
    "Weather Observation Time",
    "Weather Condition",
    "Weather Temperature",
    "Apparent Temperature",
    "Dewpoint",
    "Humidity",
    "Weather Pressure",
    "Wind Speed",
    "Wind Gust",
    "Wind Bearing",
    "Precipitation Intensity",
    "Sunrise Time",
    "Sunset Time",
    "Moon Phase",
    "Bike",
    "Gear",
    "Precipitation Probability",
    "Precipitation Type",
    "Cloud Cover",
    "Weather Visibility",
    "UV Index",
    "Weather Ozone",
    "Jump Count",
    "Total Grit",
    "Average Flow",
    "Flagged",
    "Average Elapsed Speed",
    "Dirt Distance",
    "Newly Explored Distance",
    "Newly Explored Dirt Distance",
    "Activity Count",
    "Total Steps",
    "Media",
]


def import_from_strava_checkout(repository: ActivityRepository) -> None:
    checkout_path = pathlib.Path("Strava Export")
    activities = pd.read_csv(checkout_path / "activities.csv")

    if activities.columns[0] == EXPECTED_COLUMNS[0]:
        dayfirst = False
    if activities.columns[0] == "Aktivitäts-ID":
        activities = pd.read_csv(checkout_path / "activities.csv", decimal=",")
        activities.columns = EXPECTED_COLUMNS
        dayfirst = True

    activities.index = activities["Activity ID"]
    work_tracker = WorkTracker("import-strava-checkout-activities")
    activities_ids_to_parse = work_tracker.filter(activities["Activity ID"])
    activities_ids_to_parse = [
        activity_id
        for activity_id in activities_ids_to_parse
        if not repository.has_activity(activity_id)
    ]

    activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")
    activity_stream_dir.mkdir(exist_ok=True, parents=True)

    for activity_id in tqdm(activities_ids_to_parse, desc="Import from Strava export"):
        row = activities.loc[activity_id]
        activity_file = checkout_path / row["Filename"]
        table_activity_meta = {
            "calories": row["Calories"],
            "commute": row["Commute"] == "true",
            "distance_km": row["Distance"],
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
            "start": dateutil.parser.parse(
                row["Activity Date"], dayfirst=dayfirst
            ).astimezone(datetime.timezone.utc),
        }

        time_series_path = activity_stream_dir / f"{activity_id}.parquet"
        if time_series_path.exists():
            time_series = pd.read_parquet(time_series_path)
        else:
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

        work_tracker.mark_done(activity_id)

        if not len(time_series):
            continue

        if "latitude" not in time_series.columns:
            continue

        time_series.to_parquet(time_series_path)

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
                "-",
                f"{activity_date.hour:02d}-{activity_date.minute:02d}-{activity_date.second:02d}",
                " ",
                activity_name,
            ]
            + activity_file.suffixes
        )

        activity_target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy(activity_file, activity_target)
