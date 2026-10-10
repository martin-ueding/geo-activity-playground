import datetime
import functools
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
import sqlalchemy
from tqdm import tqdm

from ...core.datamodel import (
    DB,
    DEFAULT_UNKNOWN_NAME,
    Activity,
    ActivityImportConfig,
    get_or_make_equipment,
    get_or_make_kind,
)
from ...core.duplicate_matching import check_for_duplicate
from ...core.paths import activity_extracted_meta_dir
from ...core.pipeline import ingest_parsed_activity, keep_trim_indices
from ...core.tasks import WorkTracker, work_tracker_path
from ...importers.activity_parsers import (
    ActivityParseError,
    NoGeoDataError,
    read_activity,
)
from .csv_parser import parse_csv
from .upstream import is_strava_activity_excluded

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
    with open(
        pathlib.Path(__file__).parent / "strava-csv-mapping.json", encoding="utf-8"
    ) as f:
        mapping = json.load(f)
    return [mapping.get(h, h) for h in header]


INGEST_VERSION = 3

CHECKOUT_PATH = pathlib.Path("Strava Export")


def read_checkout_rows() -> tuple[dict[int, dict[str, str]], bool]:
    """The rows of `activities.csv` by activity ID, and whether dates are day first."""
    csv_path = CHECKOUT_PATH / "activities.csv"
    return _read_checkout_rows(csv_path, csv_path.stat().st_mtime_ns)


@functools.cache
def _read_checkout_rows(
    csv_path: pathlib.Path,
    mtime_ns: int,  # noqa: ARG001
) -> tuple[dict[int, dict[str, str]], bool]:
    with open(csv_path, encoding="utf-8") as f:
        rows = parse_csv(f.read())
    header = rows[0]
    logger.debug("Strava checkout header: %s", json.dumps(header, ensure_ascii=False))

    if header[0] == "Activity ID":
        logger.debug("Detected EN Strava checkout header.")
        dayfirst = False
    elif header[0] == "Aktivitäts-ID":
        logger.debug("Detected DE Strava checkout header, normalizing to EN columns.")
        header = normalize_header(header)
        dayfirst = True
        logger.debug(
            "Strava checkout header (normalized to EN columns): %s",
            json.dumps(header, ensure_ascii=False),
        )
    else:
        logger.debug("Detected unknown Strava checkout header format.")
        logger.error(
            "You are trying to import a Strava checkout where the `activities.csv` contains an unexpected header format. In order to import this, we need to map these to the English ones. Unfortunately Strava often changes the number of columns. This means that the program needs to be updated to match the new Strava export format. Please go to https://github.com/martin-ueding/geo-activity-playground/issues and open a new issue and share the following output in the ticket:"
        )
        print(header)
        sys.exit(1)

    if "Activity ID" not in header:
        logger.error(
            "Could not find required column 'Activity ID' in Strava checkout header. "
            "Please open an issue at https://github.com/martin-ueding/geo-activity-playground/issues "
            "and paste the following JSON header there:"
        )
        print(json.dumps(header, ensure_ascii=False))
        sys.exit(1)

    rows_by_id = {}
    for values in rows[1:]:
        row = dict(zip(header, values))
        rows_by_id[int(row["Activity ID"])] = row
    return rows_by_id, dayfirst


def parse_checkout_row(
    row: dict[str, str], dayfirst: bool
) -> tuple[Activity, pd.DataFrame]:
    """Read the activity file of a row and overlay what `activities.csv` states.

    Raises the parser errors of `read_activity`.
    """
    activity_file = CHECKOUT_PATH / row["Filename"]
    activity, time_series = read_activity(activity_file)

    activity.path = str(activity_file)
    activity.start = dateutil.parser.parse(
        row["Activity Date"], dayfirst=dayfirst
    ).replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    activity.calories = float_with_comma_or_period(row["Calories"])
    activity.distance_km = row["Distance"]
    activity.elapsed_time = datetime.timedelta(
        seconds=float_with_comma_or_period(row["Elapsed Time"])
    )
    activity.steps = float_with_comma_or_period(row["Total Steps"])
    activity.name = row["Activity Name"]
    if row["Activity Type"]:
        activity.kind = get_or_make_kind(row["Activity Type"])
    if equipment := (
        nan_as_none(row["Activity Gear"])
        or nan_as_none(row["Bike"])
        or nan_as_none(row["Gear"])
    ):
        activity.equipment = get_or_make_equipment(equipment)
    return activity, time_series


def import_from_strava_checkout(
    config: ActivityImportConfig,
    source: str | None = None,
) -> None:
    rows_by_id, dayfirst = read_checkout_rows()

    work_tracker = WorkTracker(work_tracker_path("import-strava-checkout-activities"))
    activities_ids_to_parse = work_tracker.filter(list(rows_by_id))
    activities_ids_to_parse = [
        activity_id
        for activity_id in activities_ids_to_parse
        if not (activity_extracted_meta_dir() / f"{activity_id}.pickle").exists()
        and not is_strava_activity_excluded(activity_id)
    ]

    for activity_id in tqdm(activities_ids_to_parse, desc="Import from Strava export"):
        row = rows_by_id[activity_id]

        # Some manually recorded activities have no file name. Pandas reads that as a float. We skip those.
        if not row["Filename"]:
            work_tracker.mark_done(activity_id)
            continue

        if (
            existing_activity := DB.session.scalar(
                sqlalchemy.select(Activity).where(
                    Activity.upstream_id == str(activity_id)
                )
            )
        ) is not None:
            logger.info(
                f"Strava activity {activity_id} already exists in database as {existing_activity.id}, skipping."
            )
            work_tracker.mark_done(activity_id)
            continue

        logger.info(f"Importing '{row['Filename']}' …")

        try:
            activity, time_series = parse_checkout_row(row, dayfirst)
        except NoGeoDataError:
            logger.warning(f"Skipping `{row['Filename']}` due to missing geo data.")
            logger.debug(f"Parser traceback for `{row['Filename']}`", exc_info=True)
            work_tracker.mark_done(activity_id)
            continue
        except ActivityParseError:
            logger.error(f"Error while parsing `{row['Filename']}`:")
            traceback.print_exc()
            continue

        work_tracker.mark_done(activity_id)

        if not len(time_series):
            continue

        if "latitude" not in time_series.columns:
            continue

        activity.upstream_id = str(activity_id)
        activity.source = source
        ingest_parsed_activity(activity, activity, time_series, config, INGEST_VERSION)
        check_for_duplicate(activity, config)

    work_tracker.close()


def reingest_checkout_activity(
    activity: Activity, config: ActivityImportConfig
) -> bool:
    """Run the ingest stage again from the activity file and its `activities.csv` row."""
    if not activity.upstream_id or not (CHECKOUT_PATH / "activities.csv").exists():
        return False
    rows_by_id, dayfirst = read_checkout_rows()
    row = rows_by_id.get(int(activity.upstream_id))
    if row is None or not row["Filename"]:
        logger.warning(
            "Cannot re-ingest activity %s, Strava activity %s is not in the export.",
            activity.id,
            activity.upstream_id,
        )
        return False
    if not (CHECKOUT_PATH / row["Filename"]).exists():
        logger.warning(
            "Cannot re-ingest activity %s, %s is gone.", activity.id, row["Filename"]
        )
        return False

    try:
        parsed, time_series = parse_checkout_row(row, dayfirst)
    except (ActivityParseError, NoGeoDataError):
        logger.warning(
            "Cannot re-ingest activity %s from %s.",
            activity.id,
            row["Filename"],
            exc_info=True,
        )
        return False

    keep_trim_indices(activity, time_series)
    ingest_parsed_activity(
        activity,
        parsed,
        time_series,
        config,
        INGEST_VERSION,
        force_enrichment=True,
    )
    return True


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
