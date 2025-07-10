import datetime
import logging
import pathlib
import pickle
import time
import zoneinfo

import pandas as pd
from stravalib import Client
from stravalib.exc import Fault
from stravalib.exc import ObjectNotFound
from stravalib.exc import RateLimitExceeded
from tqdm import tqdm

from ..core.activities import ActivityRepository
from ..core.config import Config
from ..core.datamodel import Activity
from ..core.datamodel import DB
from ..core.datamodel import get_or_make_equipment
from ..core.datamodel import get_or_make_kind
from ..core.enrichment import apply_enrichments
from ..core.enrichment import update_and_commit
from ..core.paths import activity_extracted_time_series_dir
from ..core.paths import strava_api_dir
from ..core.paths import strava_last_activity_date_path
from ..core.tasks import get_state
from ..core.tasks import set_state
from ..explorer.tile_visits import compute_tile_evolution
from ..explorer.tile_visits import compute_tile_visits_new
from ..explorer.tile_visits import TileVisitAccessor


logger = logging.getLogger(__name__)


def get_current_access_token(config: Config) -> str:
    tokens = get_state(strava_api_dir() / "strava_tokens.json", None)
    if not tokens:
        logger.info("Create Strava access token …")
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=config.strava_client_id,
            client_secret=config.strava_client_secret,
            code=config.strava_client_code,
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
            client_id=config.strava_client_id,
            client_secret=config.strava_client_secret,
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


def import_from_strava_api(
    config: Config,
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
) -> None:
    while try_import_strava(config, repository, tile_visit_accessor):
        now = datetime.datetime.now()
        next_quarter = round_to_next_quarter_hour(now)
        seconds_to_wait = (next_quarter - now).total_seconds() + 10
        logger.warning(
            f"Strava rate limit exceeded, will try again at {next_quarter.isoformat()}."
        )
        time.sleep(seconds_to_wait)


def try_import_strava(
    config: Config,
    repository: ActivityRepository,
    tile_visit_accessor: TileVisitAccessor,
) -> bool:
    get_after = get_state(strava_last_activity_date_path(), "2000-01-01T00:00:00Z")

    gear_names = {None: "None"}

    client = Client(access_token=get_current_access_token(config))

    try:
        for strava_activity in tqdm(
            client.get_activities(after=get_after), desc="Downloading Strava activities"
        ):
            cache_file = (
                pathlib.Path("Cache")
                / "Strava Activity Metadata"
                / f"{strava_activity.id}.pickle"
            )
            # Sometimes we still get an activity here although it has already been imported from the Strava checkout.
            if cache_file.exists():
                continue
            cache_file.parent.mkdir(exist_ok=True, parents=True)
            with open(cache_file, "wb") as f:
                pickle.dump(strava_activity, f)
            if strava_activity.gear_id not in gear_names:
                gear = client.get_gear(strava_activity.gear_id)
                gear_names[strava_activity.gear_id] = (
                    f"{gear.name}" or f"{gear.brand_name} {gear.model_name}"
                )

            time_series_path = (
                activity_extracted_time_series_dir() / f"{strava_activity.id}.parquet"
            )
            if time_series_path.exists():
                time_series = pd.read_parquet(time_series_path)
            else:
                try:
                    time_series = download_strava_time_series(
                        strava_activity.id, client
                    )
                except ObjectNotFound as e:
                    logger.error(
                        f"The activity {strava_activity.id} with name “{strava_activity.name}” cannot be found."
                        f"Perhaps it is a manual activity without a time series. Ignoring. {e=}"
                    )
                    continue
                time_series.name = strava_activity.id
                new_time = [
                    strava_activity.start_date + datetime.timedelta(seconds=time)
                    for time in time_series["time"]
                ]
                del time_series["time"]
                time_series["time"] = new_time
                time_series.to_parquet(time_series_path)

            detailed_activity = get_detailed_activity(strava_activity.id, client)

            if len(time_series) > 0 and "latitude" in time_series.columns:
                activity = Activity()
                activity.upstream_id = str(strava_activity.id)
                activity.distance_km = strava_activity.distance / 1000
                activity.name = strava_activity.name
                activity.kind = get_or_make_kind(str(strava_activity.type.root))
                activity.start = strava_activity.start_date.astimezone(
                    zoneinfo.ZoneInfo("UTC")
                )
                activity.elapsed_time = strava_activity.elapsed_time
                activity.equipment = get_or_make_equipment(
                    gear_names[strava_activity.gear_id], config
                )
                activity.calories = detailed_activity.calories
                activity.moving_time = detailed_activity.moving_time

                update_and_commit(activity, time_series, config)
                compute_tile_visits_new(repository, tile_visit_accessor)
                compute_tile_evolution(tile_visit_accessor.tile_state, config)
                tile_visit_accessor.save()

            set_state(
                strava_last_activity_date_path(),
                strava_activity.start_date.isoformat().replace("+00:00", "Z"),
            )

        limit_exceeded = False
    except RateLimitExceeded:
        limit_exceeded = True
    except Fault as e:
        if "Too Many Requests" in str(e):
            limit_exceeded = True
        else:
            raise

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
