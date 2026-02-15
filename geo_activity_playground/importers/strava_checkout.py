import datetime
import json
import logging
import pathlib
import shutil
import sys
import traceback
import urllib.parse
import zoneinfo
from collections.abc import Sequence

import dateutil.parser
import numpy as np
import pandas as pd
from tqdm import tqdm

from ..core.config import Config
from ..core.datamodel import (
    DEFAULT_UNKNOWN_NAME,
    get_or_make_equipment,
    get_or_make_kind,
)
from ..core.enrichment import update_and_commit
from ..core.paths import activity_extracted_meta_dir
from ..core.tasks import WorkTracker, work_tracker_path
from .activity_parsers import ActivityParseError, read_activity
from .csv_parser import parse_csv

logger = logging.getLogger(__name__)


def nan_as_none(elem):
    if isinstance(elem, float) and np.isnan(elem):
        return None
    else:
        return elem


def float_with_comma_or_period(x: str) -> float | None:
    if len(x) == 0:
        return 0

    if "," in x:
        x = x.replace(",", ".")
    return float(x)


def normalize_header(header: Sequence[str]) -> list[str]:
    with open(pathlib.Path(__file__).parent / "strava-csv-mapping.json") as f:
        mapping = json.load(f)
    return [mapping.get(h, h) for h in header]


def import_from_strava_checkout(config: Config) -> None:
    checkout_path = pathlib.Path("Strava Export")
    with open(checkout_path / "activities.csv", encoding="utf-8") as f:
        rows = parse_csv(f.read())
    header = rows[0]

    if header[0] == "Activity ID":
        dayfirst = False
    elif header[0] == "Aktivitäts-ID":
        header = normalize_header(header)
        dayfirst = True
    else:
        logger.error(
            "You are trying to import a Strava checkout where the `activities.csv` contains an unexpected header format. In order to import this, we need to map these to the English ones. Unfortunately Strava often changes the number of columns. This means that the program needs to be updated to match the new Strava export format. Please go to https://github.com/martin-ueding/geo-activity-playground/issues and open a new issue and share the following output in the ticket:"
        )
        print(header)
        sys.exit(1)

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
        index = all_activity_ids.index(activity_id)
        row = {column: table[column][index] for column in header}

        # Some manually recorded activities have no file name. Pandas reads that as a float. We skip those.
        if not row["Filename"]:
            work_tracker.mark_done(activity_id)
            continue

        start_datetime = dateutil.parser.parse(
            row["Activity Date"], dayfirst=dayfirst
        ).replace(tzinfo=zoneinfo.ZoneInfo("UTC"))

        activity_file = checkout_path / row["Filename"]

        logger.info(f"Importing '{activity_file}' …")

        try:
            activity, time_series = read_activity(activity_file)
        except ActivityParseError:
            logger.error(f"Error while parsing `{activity_file}`:")
            traceback.print_exc()
            continue

        work_tracker.mark_done(activity_id)

        if not len(time_series):
            continue

        if "latitude" not in time_series.columns:
            continue

        activity.upstream_id = activity_id
        activity.calories = float_with_comma_or_period(row["Calories"])
        activity.distance_km = row["Distance"]
        activity.elapsed_time = datetime.timedelta(
            seconds=float_with_comma_or_period(row["Elapsed Time"])
        )
        activity.equipment = get_or_make_equipment(
            nan_as_none(row["Activity Gear"])
            or nan_as_none(row["Bike"])
            or nan_as_none(row["Gear"])
            or DEFAULT_UNKNOWN_NAME,
            config,
        )
        activity.kind = get_or_make_kind(row["Activity Type"])
        activity.name = row["Activity Name"]
        activity.path = str(activity_file)
        activity.start = start_datetime
        activity.steps = float_with_comma_or_period(row["Total Steps"])

        update_and_commit(activity, time_series, config)

    work_tracker.close()


def convert_strava_checkout(
    checkout_path: pathlib.Path, playground_path: pathlib.Path
) -> None:
    activities = pd.read_csv(checkout_path / "activities.csv")
    print(activities)

    # Handle German localization.
    if activities.columns[0] == "Aktivitäts-ID":
        activities.columns = normalize_header(activities.columns)

    for _, row in tqdm(activities.iterrows(), desc="Import activity files"):
        # Some people have manually added activities without position data. These don't have a file there. We'll skip these.
        if not isinstance(row["Filename"], str):
            continue

        activity_date = dateutil.parser.parse(row["Activity Date"])
        activity_name: str = row["Activity Name"]
        activity_kind = row["Activity Type"]
        equipment = (
            nan_as_none(row["Activity Gear"])
            or nan_as_none(row["Bike"])
            or nan_as_none(row["Gear"])
            or DEFAULT_UNKNOWN_NAME
        )
        activity_file = checkout_path / row["Filename"]

        activity_target = playground_path / "Activities" / str(activity_kind)
        if equipment:
            activity_target /= str(equipment)

        activity_target /= "".join(
            [
                f"{activity_date.year:04d}-{activity_date.month:02d}-{activity_date.day:02d}",
                "-",
                f"{activity_date.hour:02d}-{activity_date.minute:02d}-{activity_date.second:02d}",
                " ",
                urllib.parse.quote_plus(activity_name),
            ]
            + activity_file.suffixes
        )

        activity_target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy(activity_file, activity_target)
