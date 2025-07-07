import datetime
import json
import logging
import zoneinfo

import requests

from .paths import USER_CACHE_DIR

logger = logging.getLogger(__name__)


def sanitize_datetime(
    dt: datetime.datetime, fallback_from: str, fallback_to: str
) -> datetime.datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(fallback_from))
    return dt.astimezone(zoneinfo.ZoneInfo(fallback_to))


def get_country_timezone(latitude: float, longitude: float) -> tuple[str, str]:
    cache_file = USER_CACHE_DIR / "geotimezone" / f"{latitude:.5f}-{longitude:.5f}.json"
    data = {}
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                data = json.load(f)
        except json.decoder.JSONDecodeError as e:
            logger.warning(
                f"'{cache_file}' could not be parsed ('{e}'). Deleting and trying again."
            )
            cache_file.unlink()

    if not cache_file.exists():
        url = f"https://api.geotimezone.com/public/timezone?latitude={latitude}&longitude={longitude}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()
        cache_file.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_file, "w") as f:
            json.dump(data, f)
    return data["location"], data["iana_timezone"]
