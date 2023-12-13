import datetime
import functools
import json
import logging
import pathlib
import pickle
import sys
import time
from typing import Any

import pandas as pd
from stravalib import Client
from stravalib.exc import RateLimitExceeded
from tqdm import tqdm

from geo_activity_playground.core.config import get_config


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


def import_from_strava_api() -> None:
    while try_import_strava():
        now = datetime.datetime.now()
        next_quarter = round_to_next_quarter_hour(now)
        seconds_to_wait = (next_quarter - now).total_seconds() + 10
        logger.warning(
            f"Strava rate limit exceeded, will try again at {next_quarter.isoformat()}."
        )
        time.sleep(seconds_to_wait)


def try_import_strava() -> None:
    meta_file = pathlib.Path("Cache") / "activities.parquet"
    if meta_file.exists():
        logger.info("Loading metadata file …")
        meta = pd.read_parquet(meta_file)
        get_after = meta.iloc[-1]["start"].isoformat().replace("+00:00", "Z")
    else:
        logger.info("Didn't find a metadata file.")
        meta = None
        get_after = "2000-01-01T00:00:00Z"

    gear_names = {None: "None"}

    client = Client(access_token=get_current_access_token())

    new_rows: list[dict] = []
    try:
        for activity in tqdm(
            client.get_activities(after=get_after), desc="Downloading Strava activities"
        ):
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
                time_series = download_strava_time_series(activity.id, client)
                time_series.name = activity.id
                new_time = [
                    activity.start_date + datetime.timedelta(seconds=time)
                    for time in time_series["time"]
                ]
                del time_series["time"]
                time_series["time"] = new_time
                time_series.to_parquet(time_series_path)

            if len(time_series) > 0 and "latitude" in time_series.columns:
                new_rows.append(
                    {
                        "id": activity.id,
                        "commute": activity.commute,
                        "distance": activity.distance.magnitude,
                        "name": activity.name,
                        "kind": str(activity.type),
                        "start": activity.start_date,
                        "elapsed_time": activity.elapsed_time,
                        "equipment": gear_names[activity.gear_id],
                        "calories": activity.calories,
                    }
                )
        limit_exceeded = False
    except RateLimitExceeded:
        limit_exceeded = True

    new_df = pd.DataFrame(new_rows)
    merged: pd.DataFrame = pd.concat([meta, new_df])
    merged.sort_values("start", inplace=True)
    meta_file.parent.mkdir(exist_ok=True, parents=True)
    merged.to_parquet(meta_file)

    return limit_exceeded


def download_strava_time_series(activity_id: int, client: Client) -> pd.DataFrame:
    streams = client.get_activity_streams(
        activity_id, ["time", "latlng", "altitude", "heartrate", "temp"]
    )
    columns = {"time": streams["time"].data}
    if "latlng" in streams:
        columns["latitude"] = [elem[0] for elem in streams["latlng"].data]
        columns["longitude"] = [elem[1] for elem in streams["latlng"].data]
    for name in ["distance", "altitude", "heartrate"]:
        if name in streams:
            columns[name] = streams[name].data

    df = pd.DataFrame(columns)
    return df
