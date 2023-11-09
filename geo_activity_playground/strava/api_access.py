import argparse
import datetime
import functools
import logging
import os
import pathlib
import pickle
import shutil
from typing import Any
from typing import Iterator

import pandas as pd
from stravalib import Client
from stravalib.exc import RateLimitExceeded
from stravalib.model import Activity

from geo_activity_playground.core.activities import ActivityMeta
from geo_activity_playground.core.activities import ActivityRepository
from geo_activity_playground.core.directories import get_config
from geo_activity_playground.core.directories import get_state
from geo_activity_playground.core.directories import set_state
from geo_activity_playground.core.sources import TimeSeriesSource


logger = logging.getLogger(__name__)


@functools.cache
def strava_api_dir() -> pathlib.Path:
    result = pathlib.Path.cwd() / "Strava API"
    result.mkdir(exist_ok=True, parents=True)
    return result


@functools.cache
def activity_metadata_dir() -> pathlib.Path:
    result = strava_api_dir() / "Metadata"
    result.mkdir(exist_ok=True, parents=True)
    return result


@functools.cache
def activity_streams_dir() -> pathlib.Path:
    result = strava_api_dir() / "Data"
    result.mkdir(exist_ok=True, parents=True)
    return result


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


def download_activities_after(after: str) -> None:
    logger.info(f"Downloading activities after {after} …")
    client = Client(access_token=get_current_access_token())

    for activity in client.get_activities(after=after):
        logger.info(f"Downloaded activity {activity}.")
        start = int(activity.start_date.timestamp())
        cache_file = activity_metadata_dir() / f"{start}.pickle"
        with open(cache_file, "wb") as f:
            pickle.dump(activity, f)


def sync_activity_metadata() -> None:
    cached_activity_paths = list(activity_metadata_dir().glob("*.pickle"))
    if cached_activity_paths:
        last_activity_path = max(cached_activity_paths)
        with open(last_activity_path, "rb") as f:
            activity = pickle.load(f)
        download_activities_after(
            activity.start_date.isoformat().replace("+00:00", "Z")
        )
    else:
        download_activities_after("2000-01-01T00:00:00Z")


def iter_all_activities() -> Iterator[Activity]:
    for path in activity_metadata_dir().glob("*.pickle"):
        with open(path, "rb") as f:
            yield pickle.load(f)


def make_activity_dict(activity: Activity) -> dict[str, Any]:
    result = {
        "id": activity.id,
        "commute": activity.commute,
        "distance": activity.distance.magnitude,
        "name": activity.name,
        "type": activity.type,
        "start_date": activity.start_date,
        "elapsed_time": activity.elapsed_time,
        "gear_id": activity.gear_id,
        "calories": activity.calories,
        "description": activity.description,
        "private": activity.private,
    }
    if activity.start_latlng is not None and activity.end_latlng is not None:
        result.update(
            {
                "start_latlon": (activity.start_latlng.lat, activity.start_latlng.lon),
                "end_latlon": (activity.end_latlng.lat, activity.end_latlng.lon),
            }
        )
    return result


def make_activity(activity: Activity) -> ActivityMeta:
    return ActivityMeta(
        calories=activity.calories,
        commute=activity.commute,
        distance=activity.distance.magnitude,
        elapsed_time=activity.elapsed_time,
        equipment=activity.gear_id,
        id=int(activity.start_date.timestamp()),
        kind=activity.type,
        name=activity.name,
        start=activity.start_date,
    )


def main_parquet(options: argparse.Namespace) -> None:
    df = pd.DataFrame(map(make_activity_dict, iter_all_activities()))
    df.to_parquet(options.out_path)


def download_missing_activity_streams() -> None:
    to_download = [
        activity
        for activity in iter_all_activities()
        if not (
            activity_streams_dir() / f"{int(activity.start_date.timestamp())}.parquet"
        ).exists()
    ]
    to_download.reverse()
    if to_download:
        logger.info(f"Downloading time series data for {len(to_download)} activities …")
        client = Client(access_token=get_current_access_token())
        for activity in to_download:
            logger.info(f"Downloading time series data for activity {activity} …")
            streams = client.get_activity_streams(
                activity.id, ["time", "latlng", "altitude", "heartrate", "temp"]
            )
            columns = {}
            if "latlng" in streams:
                columns["latitude"] = [elem[0] for elem in streams["latlng"].data]
                columns["longitude"] = [elem[1] for elem in streams["latlng"].data]
            for name in ["distance", "altitude", "heartrate", "time"]:
                if name in streams:
                    columns[name] = streams[name].data
            df = pd.DataFrame(columns)
            df.name = str(activity.id)
            df.to_parquet(
                activity_streams_dir()
                / f"{int(activity.start_date.timestamp())}.parquet"
            )


class StravaAPITimeSeriesSource(TimeSeriesSource):
    def __init__(self) -> None:
        try:
            sync_activity_metadata()
            download_missing_activity_streams()
        except RateLimitExceeded as e:
            pass

    def iter_activities(self) -> Iterator[pd.DataFrame]:
        for path in activity_streams_dir().glob("*.parquet"):
            df = pd.read_parquet(path)
            df.name = path.stem
            if "latitude" not in df.columns:
                continue
            yield df


class StravaAPIActivityRepository(ActivityRepository):
    def __init__(self) -> None:
        self._client = Client(access_token=get_current_access_token())

        try:
            sync_activity_metadata()
            download_missing_activity_streams()
        except RateLimitExceeded as e:
            pass

    def iter_activities(self) -> Iterator[ActivityMeta]:
        for path in reversed(list(activity_metadata_dir().glob("*.pickle"))):
            with open(path, "rb") as f:
                strava_activity = pickle.load(f)
                yield make_activity(strava_activity)

    def get_activity_by_id(self, id: int) -> ActivityMeta:
        with open(activity_metadata_dir() / f"{id}.pickle", "rb") as f:
            strava_activity = pickle.load(f)
            return make_activity(strava_activity)

    def get_time_series(self, id: int) -> pd.DataFrame:
        return pd.read_parquet(activity_streams_dir() / f"{id}.parquet")
