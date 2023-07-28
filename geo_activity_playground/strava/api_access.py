import datetime
import logging

from stravalib import Client

from geo_activity_playground.directories import get_config
from geo_activity_playground.directories import get_state
from geo_activity_playground.directories import set_state


logger = logging.getLogger(__name__)


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
    client = Client(access_token=get_current_access_token())
    athlete = client.get_athlete()
    print(athlete)


if __name__ == "__main__":
    main()
