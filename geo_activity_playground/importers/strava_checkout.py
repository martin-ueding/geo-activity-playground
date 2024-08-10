import datetime
import logging
import pathlib
import pickle
import shutil
import sys
import traceback
from typing import Optional
from typing import Union

import dateutil.parser
import numpy as np
import pandas as pd
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.paths import activity_extracted_meta_dir
from geo_activity_playground.core.paths import activity_extracted_time_series_dir
from geo_activity_playground.core.paths import strava_last_activity_date_path
from geo_activity_playground.core.tasks import get_state
from geo_activity_playground.core.tasks import set_state
from geo_activity_playground.core.tasks import work_tracker_path
from geo_activity_playground.core.tasks import WorkTracker
from geo_activity_playground.core.time_conversion import convert_to_datetime_ns
from geo_activity_playground.importers.activity_parsers import ActivityParseError
from geo_activity_playground.importers.activity_parsers import read_activity
from geo_activity_playground.importers.csv_parser import parse_csv


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
    "Elapsed Time",
    "Moving Time",
    "Distance",
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
    "Max Heart Rate",
    "Average Heart Rate",
    "Max Watts",
    "Average Watts",
    "Calories",
    "Max Temperature",
    "Average Temperature",
    "Relative Effort",
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
    "Commute",
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
    "Carbon Saved",
    "Pool Length",
    "Training Load",
    "Intensity",
    "Average Grade Adjusted Pace",
    "Timer Time",
    "Total Cycles",
    "Media",
]


def float_with_comma_or_period(x: str) -> Optional[float]:
    if len(x) == 0:
        return 0

    if "," in x:
        x = x.replace(",", ".")
    return float(x)


def import_from_strava_checkout() -> None:
    checkout_path = pathlib.Path("Strava Export")
    with open(checkout_path / "activities.csv") as f:
        rows = parse_csv(f.read())
    header = rows[0]

    if len(header) != len(EXPECTED_COLUMNS):
        logger.error(
            f"You are trying to import a Strava checkout where the `activities.csv` contains an unexpected header format. In order to import this, we need to map these to the English ones. Unfortunately Strava often changes the number of columns. Your file has {len(header)} but we expect {len(EXPECTED_COLUMNS)}. This means that the program needs to be updated to match the new Strava export format. Please go to https://github.com/martin-ueding/geo-activity-playground/issues and open a new issue and share the following output in the ticket:"
        )
        print(header)
        sys.exit(1)

    if header[0] == EXPECTED_COLUMNS[0]:
        dayfirst = False
    if header[0] == "Aktivitäts-ID":
        header = EXPECTED_COLUMNS
        dayfirst = True

    table = {
        header[i]: [rows[r][i] for r in range(1, len(rows))] for i in range(len(header))
    }
    all_activity_ids = [int(value) for value in table["Activity ID"]]

    work_tracker = WorkTracker(work_tracker_path("import-strava-checkout-activities"))
    activities_ids_to_parse = work_tracker.filter(all_activity_ids)
    activities_ids_to_parse = [
        activity_id
        for activity_id in activities_ids_to_parse
        if not (activity_extracted_meta_dir() / f"{activity_id}.pickle").exists()
    ]

    for activity_id in tqdm(activities_ids_to_parse, desc="Import from Strava export"):
        work_tracker.mark_done(activity_id)
        index = all_activity_ids.index(activity_id)
        row = {column: table[column][index] for column in header}

        # Some manually recorded activities have no file name. Pandas reads that as a float. We skip those.
        if not row["Filename"]:
            continue

        start_datetime = dateutil.parser.parse(row["Activity Date"], dayfirst=dayfirst)

        activity_file = checkout_path / row["Filename"]
        table_activity_meta: ActivityMeta = {
            "calories": float_with_comma_or_period(row["Calories"]),
            "commute": row["Commute"] == "true",
            "distance_km": row["Distance"],
            "elapsed_time": datetime.timedelta(
                seconds=float_with_comma_or_period(row["Elapsed Time"])
            ),
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
            "start": convert_to_datetime_ns(start_datetime),
            "steps": float_with_comma_or_period(row["Total Steps"]),
        }

        time_series_path = (
            activity_extracted_time_series_dir() / f"{activity_id}.parquet"
        )
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

        if not len(time_series):
            continue

        if "latitude" not in time_series.columns:
            continue

        meta_path = activity_extracted_meta_dir() / f"{activity_id}.pickle"
        with open(meta_path, "wb") as f:
            pickle.dump(table_activity_meta, f)
        time_series.to_parquet(time_series_path)

        start_str = (
            pd.Timestamp(table_activity_meta["start"]).to_pydatetime().isoformat() + "Z"
        )
        latest_start_str = get_state(strava_last_activity_date_path(), start_str)
        set_state(strava_last_activity_date_path(), max(start_str, latest_start_str))

    work_tracker.close()


def convert_strava_checkout(
    checkout_path: pathlib.Path, playground_path: pathlib.Path
) -> None:
    activities = pd.read_csv(checkout_path / "activities.csv")
    print(activities)

    for _, row in tqdm(activities.iterrows(), desc="Import activity files"):
        # Some people have manually added activities without position data. These don't have a file there. We'll skip these.
        if not isinstance(row["Filename"], str):
            continue

        activity_date = dateutil.parser.parse(row["Activity Date"])
        activity_name = row["Activity Name"]
        activity_kind = row["Activity Type"]
        is_commute = row["Commute"] == "true" or row["Commute"] == True
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
