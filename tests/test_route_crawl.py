"""Fetch every GET route of the application against a seeded database.

Together with ``jinja2.StrictUndefined`` from the ``app`` fixture this turns
template mistakes — the class of bug that only shows up in the browser — into
test failures. It is deliberately dumb: it only asserts that a page renders.
"""

import datetime as dt

import pytest
import sqlalchemy
from flask import Flask
from werkzeug.routing import Rule

from geo_activity_playground.core.datamodel import (
    DB,
    Activity,
    Equipment,
    Kind,
    TileVisit,
)

ZOOM = 14

# Routes that a blind crawl must not fetch, with the reason why. Anything not
# listed here has to be reachable, so a new route without sample data fails the
# test instead of silently going untested.
SKIPPED_ENDPOINTS = {
    "static": "serves files, not templates",
    "authentication.logout": "changes the session of the crawl",
    "explorer.enable_zoom_level": "changes the configuration",
    "explorer.mark_inaccessible": "changes stored tile state",
    "explorer.remove_inaccessible": "changes stored tile state",
    "maintenance.delete_action": "destructive",
    "maintenance.delete_action_photo": "destructive",
    "maintenance.delete_execution": "destructive",
    "maintenance.delete_task": "destructive",
    "maintenance.edit_action": "no maintenance action is seeded",
    "maintenance.edit_task": "no maintenance task is seeded",
    "maintenance.execute_task": "no maintenance task is seeded",
    "photo.new": "no photo is seeded",
    "pictures.get": "no picture is seeded",
    "plot_builder.delete": "destructive",
    "plot_builder.edit": "no plot spec is seeded",
    "search.delete_search_query": "destructive",
    "search.save_search_query": "changes stored queries",
    "segments.delete": "destructive",
    "segments.line": "no segment is seeded",
    "segments.match_info": "no segment is seeded",
    "segments.show": "no segment is seeded",
    "settings.cluster_bookmark_delete": "destructive",
    "settings.hammerhead_callback": "needs an upstream OAuth response",
    "settings.kinds_delete": "destructive",
    "settings.strava_callback": "needs an upstream OAuth response",
    "settings.tags_edit": "no tag is seeded",
    "square_planner.delete_bookmark": "destructive",
    "upload.execute_reload": "runs a full import",
    "upload.reload": "runs a full import",
}


@pytest.fixture
def samples(seeded_app: Flask) -> dict[str, object]:
    with seeded_app.app_context():
        activity = DB.session.scalar(
            sqlalchemy.select(Activity).order_by(Activity.id).limit(1)
        )
        assert activity is not None, "the seeded database must contain activities"
        assert activity.start is not None
        tile_visit = DB.session.scalar(
            sqlalchemy.select(TileVisit).where(TileVisit.zoom == ZOOM).limit(1)
        )
        assert tile_visit is not None, "the seeded database must contain tile visits"
        equipment = DB.session.scalar(sqlalchemy.select(Equipment).limit(1))
        kind = DB.session.scalar(sqlalchemy.select(Kind).limit(1))
        assert equipment is not None and kind is not None
        time_series = activity.time_series
        start: dt.datetime = activity.start

        return {
            "activity_id": activity.id,
            "activity_name": activity.name,
            "equipment_id": equipment.id,
            "kind_id": kind.id,
            "year": start.year,
            "month": start.month,
            "day": start.day,
            "latitude": float(time_series["latitude"].iloc[0]),
            "longitude": float(time_series["longitude"].iloc[0]),
            "north": float(time_series["latitude"].max()),
            "south": float(time_series["latitude"].min()),
            "east": float(time_series["longitude"].max()),
            "west": float(time_series["longitude"].min()),
            "tile_x": tile_visit.tile_x,
            "tile_y": tile_visit.tile_y,
        }


# The ``id`` of a route means a different entity in every blueprint.
ID_SAMPLES = {
    "activity.download_original": "activity_id",
    "activity.edit": "activity_id",
    "activity.geojson_line": "activity_id",
    "activity.show": "activity_id",
    "activity.trim": "activity_id",
    "equipment.edit": "equipment_id",
    "equipment.show": "equipment_id",
    "settings.kinds_edit": "kind_id",
    "sharepic.activity": "activity_id",
}


# Routes that only work with a query string, which the crawl cannot guess.
QUERY_STRINGS = {
    "export.export": "?meta_format=parquet&activity_format=",
    "settings.cluster_bookmark_new": "?zoom={zoom}&tile_x={tile_x}&tile_y={tile_y}",
}


def _arguments_for(rule: Rule, samples: dict[str, object]) -> dict[str, object]:
    values: dict[str, object] = {}
    for argument in rule.arguments:
        match argument:
            case "id":
                values[argument] = samples[ID_SAMPLES[rule.endpoint]]
            case "name":
                values[argument] = samples["activity_name"]
            case "zoom" | "z":
                values[argument] = ZOOM
            case "x":
                values[argument] = samples["tile_x"]
            case "y":
                values[argument] = samples["tile_y"]
            case "size" | "radius":
                values[argument] = 1
            case "suffix":
                values[argument] = "geojson"
            case "scheme":
                values[argument] = "color"
            case _:
                values[argument] = samples[argument]
    return values


def _crawlable_rules(app: Flask) -> list[Rule]:
    return sorted(
        (
            rule
            for rule in app.url_map.iter_rules()
            if "GET" in (rule.methods or set())
            and rule.endpoint not in SKIPPED_ENDPOINTS
        ),
        key=lambda rule: rule.endpoint,
    )


def test_every_get_route_renders(seeded_app: Flask, samples: dict[str, object]) -> None:
    client = seeded_app.test_client()
    failures = []
    for rule in _crawlable_rules(seeded_app):
        with seeded_app.test_request_context():
            built = rule.build(_arguments_for(rule, samples))
        assert built is not None
        url = built[1] + QUERY_STRINGS.get(rule.endpoint, "").format(
            zoom=ZOOM, tile_x=samples["tile_x"], tile_y=samples["tile_y"]
        )
        try:
            status = client.get(url).status_code
        except Exception as e:
            failures.append(f"{rule.endpoint} -> {url}: {type(e).__name__}: {e}")
            continue
        if status not in (200, 302):
            failures.append(f"{rule.endpoint} -> {url}: HTTP {status}")
    assert not failures, "\n".join(failures)


def test_skip_list_has_no_stale_entries(app: Flask) -> None:
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert not (SKIPPED_ENDPOINTS.keys() - endpoints), sorted(
        SKIPPED_ENDPOINTS.keys() - endpoints
    )
