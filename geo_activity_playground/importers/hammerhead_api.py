import datetime
import logging
import pathlib
import tempfile
import time

import requests
import sqlalchemy
from tqdm import tqdm

from ..core.activities import ActivityRepository
from ..core.datamodel import (
    DB,
    Activity,
    ActivityImportConfig,
    HammerheadAuth,
    get_hammerhead_auth,
    get_or_make_kind,
)
from ..core.enrichment import update_and_commit
from .activity_parsers import ActivityParseError, read_fit_activity

logger = logging.getLogger(__name__)

HAMMERHEAD_API_BASE = "https://api.hammerhead.io/v1"
HAMMERHEAD_OAUTH_SCOPE = "activity:read"


class HammerheadAuthError(RuntimeError):
    pass


def get_current_access_token() -> str:
    auth = get_hammerhead_auth()

    if not (auth.client_id and auth.client_secret):
        raise HammerheadAuthError("Hammerhead client_id/client_secret not configured.")

    if not auth.access_token or not auth.refresh_token or auth.expires_at is None:
        if not auth.client_code:
            raise HammerheadAuthError(
                "Missing Hammerhead authorization code; reconnect on the settings page."
            )
        logger.info("Exchange Hammerhead authorization code for access token …")
        exchange_code_for_token(auth)

    if auth.expires_at is None or auth.expires_at < datetime.datetime.now(
        datetime.UTC
    ).replace(tzinfo=None):
        logger.info("Refresh Hammerhead access token …")
        _refresh_token(auth)

    assert auth.access_token is not None
    return auth.access_token


def exchange_code_for_token(auth: HammerheadAuth) -> None:
    response = requests.post(
        f"{HAMMERHEAD_API_BASE}/auth/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth.client_code,
            "client_id": auth.client_id,
            "client_secret": auth.client_secret,
            "redirect_uri": auth.redirect_uri,
        },
        timeout=30,
    )
    if not response.ok:
        raise HammerheadAuthError(
            f"Hammerhead token exchange failed: {response.status_code} {response.text}"
        )
    _apply_token_response(auth, response.json())


def _refresh_token(auth: HammerheadAuth) -> None:
    response = requests.post(
        f"{HAMMERHEAD_API_BASE}/auth/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": auth.refresh_token,
            "client_id": auth.client_id,
            "client_secret": auth.client_secret,
        },
        timeout=30,
    )
    if not response.ok:
        raise HammerheadAuthError(
            f"Hammerhead token refresh failed: {response.status_code} {response.text}"
        )
    _apply_token_response(auth, response.json())


def _apply_token_response(auth: HammerheadAuth, payload: dict) -> None:
    expires_in = int(payload.get("expires_in", 3600))
    auth.access_token = payload["access_token"]
    auth.refresh_token = payload["refresh_token"]
    auth.expires_at = datetime.datetime.now(datetime.UTC).replace(
        tzinfo=None
    ) + datetime.timedelta(seconds=expires_in - 60)
    DB.session.commit()


def import_from_hammerhead_api(
    config: ActivityImportConfig,
    repository: ActivityRepository,
    hammerhead_begin: str | None = None,
    hammerhead_end: str | None = None,
) -> None:
    try:
        while _try_import_hammerhead(
            config, repository, hammerhead_begin, hammerhead_end
        ):
            logger.warning("Hammerhead rate limit hit; sleeping for 60 seconds.")
            time.sleep(60)
    except HammerheadAuthError as e:
        logger.error(
            "Hammerhead API authentication failed, skipping Hammerhead import. "
            "Your authorization code may be expired or invalid — please re-authorize "
            f"on the settings page. Details: {e}"
        )


def _try_import_hammerhead(
    config: ActivityImportConfig,
    repository: ActivityRepository,
    hammerhead_begin: str | None,
    hammerhead_end: str | None,
) -> bool:
    access_token = get_current_access_token()
    auth = get_hammerhead_auth()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {access_token}"})

    start_date = hammerhead_begin or auth.last_activity_date

    page = 1
    per_page = 100
    rate_limited = False
    newest_seen_date: str | None = None

    while True:
        params: dict[str, object] = {"page": page, "perPage": per_page}
        if start_date:
            params["startDate"] = start_date
        response = session.get(
            f"{HAMMERHEAD_API_BASE}/api/activities", params=params, timeout=60
        )
        if response.status_code == 429:
            rate_limited = True
            break
        if response.status_code in (401, 403):
            raise HammerheadAuthError(
                f"Unauthorized listing Hammerhead activities: {response.status_code} {response.text}"
            )
        response.raise_for_status()

        payload = response.json()
        activities = payload.get("data", payload.get("activities", []))
        if not activities:
            break

        for summary in tqdm(activities, desc=f"Hammerhead page {page}", leave=False):
            created_at = summary.get("createdAt")
            if hammerhead_end and created_at and created_at[:10] > hammerhead_end:
                continue

            if _already_imported(summary["id"]):
                logger.info(
                    f"Hammerhead activity {summary['id']} already exists, skipping."
                )
                if hammerhead_begin is None and hammerhead_end is None and created_at:
                    newest_seen_date = _max_date(newest_seen_date, created_at)
                continue

            try:
                _import_one_activity(config, session, summary)
            except HammerheadAuthError:
                raise
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    rate_limited = True
                    break
                logger.error(
                    f"Failed to import Hammerhead activity {summary['id']}: {e}"
                )
                continue
            except ActivityParseError as e:
                logger.error(
                    f"Could not parse FIT for Hammerhead activity {summary['id']}: {e}"
                )
                continue

            if hammerhead_begin is None and hammerhead_end is None and created_at:
                newest_seen_date = _max_date(newest_seen_date, created_at)

        if rate_limited:
            break

        total_pages = payload.get("totalPages")
        if total_pages is not None and page >= total_pages:
            break
        if len(activities) < per_page:
            break
        page += 1

    if newest_seen_date and hammerhead_begin is None and hammerhead_end is None:
        auth.last_activity_date = newest_seen_date[:10]
        DB.session.commit()

    return rate_limited


def _already_imported(hammerhead_id: str) -> bool:
    existing = DB.session.scalar(
        sqlalchemy.select(Activity).where(Activity.upstream_id == str(hammerhead_id))
    )
    return existing is not None


def _max_date(current: str | None, candidate: str) -> str:
    if current is None or candidate > current:
        return candidate
    return current


def _import_one_activity(
    config: ActivityImportConfig, session: requests.Session, summary: dict
) -> None:
    activity_id = summary["id"]
    logger.info(
        f"Importing Hammerhead activity {activity_id} '{summary.get('name', '')}' …"
    )

    detailed = _get_detailed(session, activity_id)
    fit_bytes = _download_fit(session, activity_id)

    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as f:
        f.write(fit_bytes)
        fit_path = pathlib.Path(f.name)
    try:
        activity, time_series = read_fit_activity(fit_path, open)
    finally:
        fit_path.unlink(missing_ok=True)

    if len(time_series) == 0 or "latitude" not in time_series.columns:
        logger.warning(
            f"Hammerhead activity {activity_id} has no geographic data, skipping."
        )
        return

    activity.upstream_id = str(activity_id)
    if summary.get("name"):
        activity.name = summary["name"]
    activity_type = detailed.get("activityType") or summary.get("activityType")
    if activity_type:
        activity.kind = get_or_make_kind(str(activity_type))
    if summary.get("distance") is not None:
        activity.distance_km = float(summary["distance"]) / 1000
    if summary.get("duration") is not None:
        activity.elapsed_time = datetime.timedelta(seconds=float(summary["duration"]))

    update_and_commit(activity, time_series, config)
    logger.info(f"Added activity '{activity.name}' from Hammerhead.")


def _get_detailed(session: requests.Session, activity_id: str) -> dict:
    response = session.get(
        f"{HAMMERHEAD_API_BASE}/api/activities/{activity_id}", timeout=60
    )
    if response.status_code in (401, 403):
        raise HammerheadAuthError(
            f"Unauthorized fetching Hammerhead activity {activity_id}: {response.status_code}"
        )
    response.raise_for_status()
    return response.json()


def _download_fit(session: requests.Session, activity_id: str) -> bytes:
    response = session.get(
        f"{HAMMERHEAD_API_BASE}/api/activities/{activity_id}/file", timeout=120
    )
    if response.status_code in (401, 403):
        raise HammerheadAuthError(
            f"Unauthorized downloading FIT for {activity_id}: {response.status_code}"
        )
    response.raise_for_status()
    return response.content
