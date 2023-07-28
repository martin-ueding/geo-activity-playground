import argparse
import dataclasses
import datetime
import logging
import pickle
from typing import Any
from typing import Iterator

import pandas as pd
from stravalib import Client
from stravalib.model import Activity
from tqdm import tqdm

from geo_activity_playground.core.directories import cache_dir
from geo_activity_playground.core.directories import get_config
from geo_activity_playground.core.directories import get_state
from geo_activity_playground.core.directories import set_state


logger = logging.getLogger(__name__)

activity_cache_dir = cache_dir / "strava-activities"


def get_current_access_token() -> str:
    config = get_config()

    tokens = get_state("strava_tokens")
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
        set_state("strava_tokens", tokens)

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
        set_state("strava_tokens", tokens)

    return tokens["access"]


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    init = subparsers.add_parser("init")
    init.set_defaults(func=main_init)

    download = subparsers.add_parser("download")
    download.set_defaults(func=main_download)

    parquet = subparsers.add_parser("parquet")
    parquet.set_defaults(func=main_parquet)

    options = parser.parse_args()
    options.func(options)


def main_init(options: argparse.Namespace) -> None:
    download_activities_after("2000-01-01T00:00:00Z")


def download_activities_after(after: str) -> None:
    client = Client(access_token=get_current_access_token())
    activity_cache_dir.mkdir(exist_ok=True, parents=True)

    for activity in tqdm(
        client.get_activities(after=after),
        desc=f"Downloading Activities after {after}",
    ):
        start = int(activity.start_date.timestamp())
        cache_file = activity_cache_dir / f"start-{start}.pickle"
        with open(cache_file, "wb") as f:
            pickle.dump(activity, f)


def main_download(options: argparse.Namespace) -> None:
    last_activity_path = max(activity_cache_dir.glob("*.pickle"))
    with open(last_activity_path, "rb") as f:
        activity = pickle.load(f)
    download_activities_after(activity.start_date.isoformat().replace("+00:00", "Z"))


def iter_all_activities() -> Iterator[Activity]:
    for path in activity_cache_dir.glob("*.pickle"):
        with open(path, "rb") as f:
            yield pickle.load(f)


"""
id
commute
distance
end_latlng
gear_id
name
sport_type
start_date
start_latlng
type
upload_id
calories
description
gear
"""


def make_activity_dict(activity: Activity) -> dict[str, Any]:
    result = {
        "id": activity.id,
        "commute": activity.commute,
        "distance": activity.distance.magnitude,
        "name": activity.name,
        "type": activity.type,
        "start_date": activity.start_date,
    }
    if activity.start_latlng is not None and activity.end_latlng is not None:
        result.update(
            {
                "start_lat": activity.start_latlng.lat,
                "start_lon": activity.start_latlng.lon,
                "end_lat": activity.end_latlng.lat,
                "end_lon": activity.end_latlng.lon,
            }
        )
    return result


def main_parquet(options: argparse.Namespace) -> None:
    df = pd.DataFrame(map(make_activity_dict, iter_all_activities()))
    df.to_parquet("activities.parquet")


if __name__ == "__main__":
    main()
