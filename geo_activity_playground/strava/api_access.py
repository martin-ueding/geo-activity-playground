from stravalib import Client

from geo_activity_playground.directories import get_config
from geo_activity_playground.directories import get_state
from geo_activity_playground.directories import set_state


def main() -> None:
    config = get_config()

    tokens = get_state("strava_tokens")
    if not tokens:
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=config["strava"]["client_id"],
            client_secret=config["strava"]["client_secret"],
            code=config["strava"]["code"],
        )
        tokens = {
            "access": token_response["access_token"],
            "refresh": token_response["refresh_token"],
        }
        set_state("strava_tokens", tokens)

    client = Client(access_token=tokens["access"])
    athlete = client.get_athlete()
    print(athlete)


if __name__ == "__main__":
    main()
