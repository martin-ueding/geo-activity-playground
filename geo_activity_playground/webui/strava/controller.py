import urllib.parse
from typing import Optional


class StravaController:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

        self._client_secret: Optional[str] = None

    def connect(self) -> dict:
        return {"host": self._host, "port": self._port}

    def authorize(
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
