"""Throwaway spike: does python-garminconnect work for this project's needs?

Run it yourself, because it asks for your Garmin password and an MFA code:

    pip install "garminconnect>=0.3.19,<0.4"
    python garmin_spike.py

It checks, in this order:

1. Login with e-mail, password and MFA, without a browser.
2. That the tokens survive a round trip through a JSON string, which is how the app
   would keep them in its database.
3. Listing activities newest first, and by date oldest first.
4. Downloading the original file of one activity with GPS and parsing it with the
   project's own FIT parser.

The output has no e-mail, password, tokens or coordinates, so it can be pasted into a
chat. Delete this file and the token file afterwards.
"""

import argparse
import getpass
import io
import json
import pathlib
import tempfile
import time
import traceback
import zipfile

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

FIELDS_OF_INTEREST = [
    "activityId",
    "activityName",
    "startTimeGMT",
    "startTimeLocal",
    "activityType",
    "distance",
    "duration",
    "elapsedDuration",
    "movingDuration",
    "calories",
    "hasPolyline",
    "startLatitude",
    "manualActivity",
]


def report(step: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {step}" + (f": {detail}" if detail else ""))


def login(tokens_path: pathlib.Path) -> Garmin | None:
    if tokens_path.exists():
        print(f"Found stored tokens at {tokens_path}, trying them first.")
        client = Garmin()
        try:
            client.login(tokenstore=tokens_path.read_text())
        except Exception as e:  # noqa: BLE001
            report("login with stored tokens", False, f"{type(e).__name__}: {e}")
        else:
            report("login with stored tokens (no password, no MFA)", True)
            return client

    email = input("Garmin e-mail: ").strip()
    password = getpass.getpass("Garmin password: ")
    client = Garmin(
        email, password, prompt_mfa=lambda: input("MFA code (if asked): ").strip()
    )
    try:
        client.login()
    except GarminConnectTooManyRequestsError as e:
        report("login", False, f"rate limited, do NOT retry for a while. {e}")
        return None
    except GarminConnectAuthenticationError as e:
        report("login", False, f"authentication: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        report("login", False, f"{type(e).__name__}: {e}")
        return None
    report("login with e-mail, password and MFA", True)

    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    tokens_path.write_text(client.client.dumps())
    print(f"Tokens stored at {tokens_path}, delete the file when you are done.")
    return client


def check_token_round_trip(client: Garmin) -> None:
    dumped = client.client.dumps()
    report("tokens serialize to a JSON string", dumped.startswith("{"))
    print(f"      token JSON keys: {sorted(json.loads(dumped))}")
    fresh = Garmin()
    try:
        fresh.login(tokenstore=dumped)
        fresh.get_activities(0, 1)
    except Exception as e:  # noqa: BLE001
        report("fresh client from the JSON string", False, f"{type(e).__name__}: {e}")
        return
    report("fresh client from the JSON string can call the API", True)
    after = fresh.client.dumps()
    print(f"      tokens changed after use (refreshed): {after != dumped}")


def check_listing(client: Garmin) -> list[dict]:
    activities = client.get_activities(0, 5)
    report("get_activities(0, 5)", isinstance(activities, list) and bool(activities))
    if not activities:
        return []
    first = activities[0]
    print(f"      all keys of an activity: {sorted(first)}")
    for name in FIELDS_OF_INTEREST:
        value = first.get(name, "<missing>")
        if name == "startLatitude":
            value = "<present>" if first.get(name) is not None else "<none>"
        if name == "activityType" and isinstance(value, dict):
            value = {k: value.get(k) for k in ("typeKey", "typeId", "parentTypeId")}
        print(f"      {name} = {value!r}")

    start_times = [a.get("startTimeGMT") for a in activities]
    report(
        "get_activities is newest first",
        start_times == sorted(start_times, reverse=True),
        str(start_times),
    )

    day = str(first["startTimeGMT"])[:10]
    by_date = client.get_activities_by_date(day, day, sortorder="asc")
    report(
        "get_activities_by_date(day, day, sortorder='asc') finds the newest activity",
        any(a["activityId"] == first["activityId"] for a in by_date),
        f"{len(by_date)} activities on {day}",
    )
    return activities


def check_download(client: Garmin, activities: list[dict]) -> None:
    from geo_activity_playground.importers.activity_parsers import read_fit_activity

    candidates = [a for a in activities if a.get("startLatitude") is not None]
    if not candidates:
        report("download", False, "none of the 5 newest activities has GPS")
        return
    activity_id = str(candidates[0]["activityId"])

    started = time.monotonic()
    data = client.download_activity(
        activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
    )
    report(
        "download_activity(ORIGINAL)",
        True,
        f"{len(data)} bytes in {time.monotonic() - started:.1f} s",
    )

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        report("original is a zip", False, f"starts with {data[:8]!r}")
        return
    names = archive.namelist()
    report("original is a zip", True, f"members: {names}")

    fit_names = [n for n in names if n.lower().endswith(".fit")]
    if len(fit_names) != 1:
        report("exactly one .fit in the zip", False, str(names))
        return
    report("exactly one .fit in the zip", True)

    with tempfile.TemporaryDirectory() as directory:
        fit_path = pathlib.Path(directory) / "activity.fit"
        fit_path.write_bytes(archive.read(fit_names[0]))
        try:
            _, time_series = read_fit_activity(fit_path, open)
        except Exception:  # noqa: BLE001
            report("project's read_fit_activity parses it", False)
            traceback.print_exc()
            return
    report(
        "project's read_fit_activity parses it",
        len(time_series) > 0 and "latitude" in time_series.columns,
        f"{len(time_series)} rows, columns {list(time_series.columns)}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tokens",
        type=pathlib.Path,
        default=pathlib.Path(tempfile.gettempdir()) / "garmin-spike" / "tokens.json",
        help="Where to keep the tokens between runs (default: %(default)s)",
    )
    options = parser.parse_args()

    client = login(options.tokens)
    if client is None:
        return
    try:
        check_token_round_trip(client)
        activities = check_listing(client)
        check_download(client, activities)
    except Exception as e:  # noqa: BLE001
        report("unexpected error", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
