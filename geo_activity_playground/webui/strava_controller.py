import urllib.parse
from typing import Optional


class StravaController:
    def __init__(self) -> None:
        self._client_secret: Optional[str] = None

    def action_connect(self) -> dict:
        return {}

    def action_authorize(
        self, host: str, port: int, client_id: str, client_secret: str
    ) -> str:
        self._client_secret = client_secret

        payload = {
            "client_id": client_id,
            "redirect_uri": f"http://{host}:{port}/strava/callback",
            "response_type": "code",
            "scope": "activity:read_all",
        }

        arg_string = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in payload.items()
        )
        return f"https://www.strava.com/oauth/authorize?{arg_string}"
