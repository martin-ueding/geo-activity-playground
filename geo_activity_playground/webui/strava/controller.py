import json
import urllib.parse
from typing import Optional

from geo_activity_playground.core.paths import strava_dynamic_config_path


class StravaController:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

        self._client_secret: Optional[str] = None

    def set_client_id(self) -> dict:
        return {"host": self._host, "port": self._port}

    def save_client_id(self, client_id: str, client_secret: str) -> str:
        self._client_id = client_id
        self._client_secret = client_secret

        payload = {
            "client_id": client_id,
            "redirect_uri": f"http://{self._host}:{self._port}/strava/callback",
            "response_type": "code",
            "scope": "activity:read_all",
        }

        arg_string = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in payload.items()
        )
        return f"https://www.strava.com/oauth/authorize?{arg_string}"

    def save_code(self, code: str) -> dict:
        self._code = code

        with open(strava_dynamic_config_path(), "w") as f:
            json.dump(
                {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": self._code,
                },
                f,
                indent=2,
                sort_keys=True,
            )

        return {}
