import datetime
import json
import zoneinfo

import requests

from .paths import USER_CACHE_DIR


def sanitize_datetime(
    dt: datetime.datetime, fallback_from: str, fallback_to: str
) -> datetime.datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(fallback_from))
    return dt.astimezone(zoneinfo.ZoneInfo(fallback_to))


def get_country_timezone(latitude: float, longitude: float) -> tuple[str, str]:
    cache_file = USER_CACHE_DIR / "geotimezone" / f"{latitude:.5f}-{longitude:.5f}.json"
    if not cache_file.exists():
        url = f"https://api.geotimezone.com/public/timezone?latitude={latitude}&longitude={longitude}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()
        cache_file.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_file, "w") as f:
            json.dump(data, f)
    else:
        with open(cache_file) as f:
            data = json.load(f)
    return data["location"], data["iana_timezone"]
