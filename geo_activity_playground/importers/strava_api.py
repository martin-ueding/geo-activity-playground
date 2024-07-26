import datetime
import functools
import json
import logging
import pathlib
import pickle
import time
from typing import Any

import pandas as pd
from stravalib import Client
from stravalib.exc import Fault
from stravalib.exc import ObjectNotFound
from stravalib.exc import RateLimitExceeded
from tqdm import tqdm

from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.config import get_config
from geo_activity_playground.core.paths import cache_dir


logger = logging.getLogger(__name__)


def get_state(path: pathlib.Path) -> Any:
    if path.exists():
        with open(path) as f:
            return json.load(f)


def set_state(path: pathlib.Path, state: Any) -> None:
    path.parent.mkdir(exist_ok=True, parents=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)


@functools.cache
def strava_api_dir() -> pathlib.Path:
    result = pathlib.Path.cwd() / "Strava API"
    result.mkdir(exist_ok=True, parents=True)
    return result


@functools.cache
def activity_stream_dir() -> pathlib.Path:
    path = pathlib.Path("Cache/Activity Timeseries")
    path.mkdir(exist_ok=True, parents=True)
    return path


def get_current_access_token() -> str:
    config = get_config()

    tokens = get_state(strava_api_dir() / "strava_tokens.json")
    if not tokens:
        logger.info("Create Strava access token …")
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=config["strava"]["client_id"],
            client_secret=config["strava"]["client_secret"],
            code=config["strava"]["code"],
        )
        tokens = {
            "access": token_response["access_token"],
            "refresh": token_response["refresh_token"],
            "expires_at": token_response["expires_at"],
        }

    if tokens["expires_at"] < datetime.datetime.now().timestamp():
        logger.info("Renew Strava access token …")
        client = Client()
        token_response = client.refresh_access_token(
            client_id=config["strava"]["client_id"],
            client_secret=config["strava"]["client_secret"],
            refresh_token=tokens["refresh"],
        )
        tokens = {
            "access": token_response["access_token"],
            "refresh": token_response["refresh_token"],
            "expires_at": token_response["expires_at"],
        }

    set_state(strava_api_dir() / "strava_tokens.json", tokens)

    return tokens["access"]


def round_to_next_quarter_hour(date: datetime.datetime) -> datetime.datetime:
    previous_quarter = datetime.datetime(
        date.year, date.month, date.day, date.hour, date.minute // 15 * 15, 0
    )
    next_quarter = previous_quarter + datetime.timedelta(minutes=15)
    return next_quarter


def import_from_strava_api(repository: ActivityRepository) -> None:
    while try_import_strava(repository):
        now = datetime.datetime.now()
        next_quarter = round_to_next_quarter_hour(now)
        seconds_to_wait = (next_quarter - now).total_seconds() + 10
        logger.warning(
            f"Strava rate limit exceeded, will try again at {next_quarter.isoformat()}."
        )
        time.sleep(seconds_to_wait)


def try_import_strava(repository: ActivityRepository) -> bool:
    last = repository.last_activity_date()
    if last is None:
        get_after = "2000-01-01T00:00:00Z"
    else:
        get_after = last.isoformat().replace("+00:00", "Z")

    gear_names = {None: "None"}

    client = Client(access_token=get_current_access_token())

    try:
        for activity in tqdm(
            client.get_activities(after=get_after), desc="Downloading Strava activities"
        ):
            # Sometimes we still get an activity here although it has already been imported from the Strava checkout.
            if repository.has_activity(activity.id):
                continue
            cache_file = (
                pathlib.Path("Cache") / "Activity Metadata" / f"{activity.id}.pickle"
            )
            cache_file.parent.mkdir(exist_ok=True, parents=True)
            with open(cache_file, "wb") as f:
                pickle.dump(activity, f)
            if not activity.gear_id in gear_names:
                gear = client.get_gear(activity.gear_id)
                gear_names[activity.gear_id] = (
                    f"{gear.name}" or f"{gear.brand_name} {gear.model_name}"
                )

            time_series_path = activity_stream_dir() / f"{activity.id}.parquet"
            if time_series_path.exists():
                time_series = pd.read_parquet(time_series_path)
            else:
                try:
                    time_series = download_strava_time_series(activity.id, client)
                except ObjectNotFound as e:
                    logger.error(
                        f"The activity {activity.id} with name “{activity.name}” cannot be found."
                        f"Perhaps it is a manual activity without a time series. Ignoring. {e=}"
                    )
                    continue
                time_series.name = activity.id
                new_time = [
                    activity.start_date + datetime.timedelta(seconds=time)
                    for time in time_series["time"]
                ]
                del time_series["time"]
                time_series["time"] = new_time
                time_series.to_parquet(time_series_path)

            detailed_activity = get_detailed_activity(activity.id, client)

            if len(time_series) > 0 and "latitude" in time_series.columns:
                repository.add_activity(
                    {
                        "id": activity.id,
                        "commute": activity.commute,
                        "distance_km": activity.distance.magnitude / 1000,
                        "name": activity.name,
                        "kind": str(activity.type),
                        "start": activity.start_date,
                        "elapsed_time": activity.elapsed_time,
                        "equipment": gear_names[activity.gear_id],
                        "calories": detailed_activity.calories,
                    }
                )
        limit_exceeded = False
    except RateLimitExceeded:
        limit_exceeded = True
    except Fault as e:
        if "Too Many Requests" in str(e):
            limit_exceeded = True
        else:
            raise

    repository.commit()

    return limit_exceeded


def download_strava_time_series(activity_id: int, client: Client) -> pd.DataFrame:
    streams = client.get_activity_streams(
        activity_id, ["time", "latlng", "altitude", "heartrate", "temp"]
    )
    columns = {"time": streams["time"].data}
    if "latlng" in streams:
        columns["latitude"] = [elem[0] for elem in streams["latlng"].data]
        columns["longitude"] = [elem[1] for elem in streams["latlng"].data]
    for name in ["altitude", "heartrate"]:
        if name in streams:
            columns[name] = streams[name].data
    if "distance" in streams:
        columns["distance_km"] = pd.Series(streams["distance"].data) / 1000

    df = pd.DataFrame(columns)
    return df


def get_detailed_activity(activity_id: int, client: Client):
    detailed_activity_path = pathlib.Path(
        f"Cache/Detailed Activities/{activity_id}.pickle"
    )
    if detailed_activity_path.exists():
        with open(detailed_activity_path, "rb") as f:
            return pickle.load(f)

    detailed_activity = client.get_activity(activity_id)

    detailed_activity_path.parent.mkdir(parents=True, exist_ok=True)
    with open(detailed_activity_path, "wb") as f:
        pickle.dump(detailed_activity, f)

    return detailed_activity
