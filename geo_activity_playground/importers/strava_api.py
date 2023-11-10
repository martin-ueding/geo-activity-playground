import datetime
import functools
import json
import logging
import pathlib
import pickle
import tomllib
from typing import Any

import pandas as pd
from stravalib import Client
from stravalib.exc import RateLimitExceeded


logger = logging.getLogger(__name__)


@functools.cache
def get_config() -> dict:
    config_path = pathlib.Path("config.toml")
    with open(config_path, "rb") as f:
        return tomllib.load(f)


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


activity_stream_dir = pathlib.Path("Cache/Activity Timeseries")


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
            "expires_at": token_response["refresh"],
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


def import_from_strava_api() -> None:
    meta_file = pathlib.Path("Cache") / "activities.parquet"
    if meta_file.exists():
        logger.info("Loading metadata file …")
        meta = pd.read_parquet(meta_file)
        get_after = meta.iloc[-1]["start"].isoformat().replace("+00:00", "Z")
    else:
        logger.info("Didn't find a metadata file.")
        meta = None
        get_after = "2000-01-01T00:00:00Z"

    client = Client(access_token=get_current_access_token())

    new_rows: list[dict] = []
    for activity in client.get_activities(after=get_after):
        logger.info(f"Downloaded Strava activity {activity.id}.")
        cache_file = (
            pathlib.Path("Cache") / "Activity Metadata" / f"{activity.id}.pickle"
        )
        cache_file.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_file, "wb") as f:
            pickle.dump(activity, f)
        new_rows.append(
            {
                "id": activity.id,
                "commute": activity.commute,
                "distance": activity.distance.magnitude,
                "name": activity.name,
                "kind": str(activity.type),
                "start": activity.start_date,
                "elapsed_time": activity.elapsed_time,
                "equipment": activity.gear_id,
                "calories": activity.calories,
            }
        )

    new_df = pd.DataFrame(new_rows)
    merged: pd.DataFrame = pd.concat([meta, new_df])
    merged.sort_values("start", inplace=True)
    meta_file.parent.mkdir(exist_ok=True, parents=True)
    merged.to_parquet(meta_file)

    download_missing_activity_streams()


def download_missing_activity_streams() -> None:
    logger.info(f"Checking for missing time series data …")
    meta_file = pathlib.Path("Cache") / "activities.parquet"
    meta = pd.read_parquet(meta_file)

    to_download = [
        id for id in meta["id"] if not (activity_stream_dir / f"{id}.parquet").exists()
    ]
    to_download.reverse()
    if to_download:
        logger.info(f"Downloading time series data for {len(to_download)} activities …")
        activity_stream_dir.mkdir(exist_ok=True, parents=True)
        client = Client(access_token=get_current_access_token())
        for id in to_download:
            logger.info(f"Downloading time series data for activity {id} …")
            streams = client.get_activity_streams(
                id, ["time", "latlng", "altitude", "heartrate", "temp"]
            )
            columns = {}
            if "latlng" in streams:
                columns["latitude"] = [elem[0] for elem in streams["latlng"].data]
                columns["longitude"] = [elem[1] for elem in streams["latlng"].data]
            for name in ["distance", "altitude", "heartrate", "time"]:
                if name in streams:
                    columns[name] = streams[name].data
            df = pd.DataFrame(columns)
            df.name = str(id)
            df.to_parquet(activity_stream_dir / f"{id}.parquet")
