import datetime
import io
import logging
import time
import zipfile
from collections.abc import Callable
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from ...core.datamodel import DB, Activity, ActivityImportConfig
from ...core.fit_api_import import (
    FitApiMetadata,
    already_imported,
    import_stored_fit,
    newest_date,
    reingest_stored_fit,
    store_artifacts,
)
from ...core.import_exclusion import record_exclusion
from ...core.paths import garmin_fit_dir
from ...importers.activity_parsers import ActivityParseError
from .model import GarminAuth, get_garmin_auth

logger = logging.getLogger(__name__)

INGEST_VERSION = 1
SOURCE = "garmin"

# Garmin does not document any limits, so the downloads are spread out a little.
SECONDS_BETWEEN_DOWNLOADS = 1.0


class GarminAuthError(RuntimeError):
    pass


def create_client(auth: GarminAuth) -> Garmin:
    """A client that is logged in with the stored tokens, which needs no password."""
    if not auth.token_json:
        raise GarminAuthError("Not connected to Garmin; log in on the settings page.")
    client = Garmin()
    try:
        client.login(tokenstore=auth.token_json)
    except GarminConnectAuthenticationError as e:
        raise GarminAuthError(f"Garmin rejected the stored tokens: {e}") from e
    return client


def store_tokens(auth: GarminAuth, client: Garmin) -> None:
    """Keep the tokens of the client, which refreshes them while it is in use."""
    auth.token_json = client.client.dumps()
    DB.session.commit()


def start_login(email: str, password: str) -> tuple[Garmin, bool]:
    """Log in with the credentials, or get as far as Garmin asking for an MFA code.

    The client that is waiting for the code is the only holder of that state, so the
    caller has to keep it around until `finish_login` is called with it.
    """
    client = Garmin(email, password, return_on_mfa=True)
    mfa_status, _ = client.login()
    return client, mfa_status == "needs_mfa"


def finish_login(client: Garmin, mfa_code: str) -> None:
    client.resume_login({}, mfa_code)


def login_interactively(
    email: str, password: str, prompt_mfa: Callable[[], str]
) -> Garmin:
    client = Garmin(email, password, prompt_mfa=prompt_mfa)
    client.login()
    return client


def import_from_garmin(
    config: ActivityImportConfig,
    garmin_begin: str | None = None,
    garmin_end: str | None = None,
    source: str = SOURCE,
) -> None:
    auth = get_garmin_auth()
    client: Garmin | None = None
    try:
        client = create_client(auth)
        _import_activities(config, auth, client, garmin_begin, garmin_end, source)
    except GarminAuthError as e:
        logger.error(
            "Garmin authentication failed, skipping Garmin import. "
            "Please log in again on the settings page. "
            f"Details: {e}"
        )
    except GarminConnectTooManyRequestsError as e:
        # Trying again right away would only prolong a block, so the next scan
        # picks up where this one stopped.
        logger.warning(
            f"Garmin rate limit exceeded, stopping the Garmin import for now. {e}"
        )
    finally:
        if client is not None:
            store_tokens(auth, client)


def _import_activities(
    config: ActivityImportConfig,
    auth: GarminAuth,
    client: Garmin,
    garmin_begin: str | None,
    garmin_end: str | None,
    source: str,
) -> None:
    start_date = garmin_begin or auth.last_activity_date or "2000-01-01"
    end_date = garmin_end or (
        datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    ).strftime("%Y-%m-%d")
    update_cursor = garmin_begin is None and garmin_end is None

    summaries = client.get_activities_by_date(start_date, end_date, sortorder="asc")
    logger.info(f"Garmin lists {len(summaries)} activities from {start_date}.")

    # The cursor must not move past an activity that failed, or it would never be
    # tried again.
    cursor_blocked = False
    for summary in summaries:
        activity_id = str(summary["activityId"])
        start = str(summary.get("startTimeGMT") or "")

        if already_imported(source, activity_id):
            logger.info(f"Garmin activity {activity_id} already exists, skipping.")
        else:
            try:
                _import_one_activity(config, client, summary, source)
            except GarminConnectAuthenticationError as e:
                raise GarminAuthError(str(e)) from e
            except GarminConnectTooManyRequestsError:
                raise
            except (
                GarminConnectConnectionError,
                ActivityParseError,
                zipfile.BadZipFile,
            ):
                logger.exception(f"Failed to import Garmin activity {activity_id}.")
                cursor_blocked = True
            time.sleep(SECONDS_BETWEEN_DOWNLOADS)

        if update_cursor and not cursor_blocked and start:
            auth.last_activity_date = newest_date(auth.last_activity_date, start[:10])
            DB.session.commit()


def _read_metadata(payload: dict[str, Any]) -> FitApiMetadata:
    summary = payload["summary"]
    activity_type = summary.get("activityType")
    type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
    seconds = summary.get("elapsedDuration") or summary.get("duration")
    return FitApiMetadata(
        name=summary.get("activityName"),
        kind=str(type_key) if type_key else None,
        distance_km=(
            float(summary["distance"]) / 1000
            if summary.get("distance") is not None
            else None
        ),
        elapsed_time=(
            datetime.timedelta(seconds=float(seconds)) if seconds is not None else None
        ),
    )


def reingest_garmin_activity(activity: Activity, config: ActivityImportConfig) -> bool:
    """Run the ingest stage again from the kept FIT file and summary."""
    return reingest_stored_fit(
        activity,
        config,
        directory=garmin_fit_dir(),
        ingest_version=INGEST_VERSION,
        read_metadata=_read_metadata,
    )


def extract_fit(original: bytes) -> bytes:
    """The FIT file inside the zip that Garmin hands out as the original."""
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".fit")]
        if len(names) != 1:
            raise zipfile.BadZipFile(
                f"Expected exactly one FIT file in the archive, found {archive.namelist()}"
            )
        return archive.read(names[0])


def _import_one_activity(
    config: ActivityImportConfig,
    client: Garmin,
    summary: dict[str, Any],
    source: str,
) -> None:
    activity_id = str(summary["activityId"])
    logger.info(
        f"Importing Garmin activity {activity_id} '{summary.get('activityName', '')}' …"
    )

    if summary.get("manualActivity"):
        logger.info(f"Garmin activity {activity_id} was entered by hand, skipping.")
        record_exclusion(source, activity_id, "no_geo_data")
        return

    original = client.download_activity(
        activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
    )
    store_artifacts(
        garmin_fit_dir(), activity_id, extract_fit(original), {"summary": summary}
    )
    import_stored_fit(
        config,
        source=source,
        ingest_version=INGEST_VERSION,
        directory=garmin_fit_dir(),
        upstream_id=activity_id,
        metadata=_read_metadata({"summary": summary}),
    )
