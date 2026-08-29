import datetime
import re

import sqlalchemy
from flask import Flask
from flask.testing import FlaskClient

from geo_activity_playground.core.datamodel import DB, Activity
from geo_activity_playground.features.activity_photos.model import Photo


def _navbar(html: str) -> str:
    return html.split('<nav class="navbar', 1)[1].split("</nav>", 1)[0]


def _nav_links(html: str) -> list[tuple[str, str]]:
    return re.findall(r'<a\s+class="([^"]*)"\s+href="([^"]*)"', _navbar(html))


def _active_hrefs(html: str) -> set[str]:
    return {href for classes, href in _nav_links(html) if "active" in classes.split()}


def test_dropdown_entry_and_its_group_are_active(seeded_client: FlaskClient) -> None:
    html = seeded_client.get("/summary/").data.decode()
    assert "/summary/" in _active_hrefs(html)
    assert re.search(
        r'class="nav-link dropdown-toggle active"[^>]*>\s*Statistics', _navbar(html)
    )


def test_sub_pages_keep_their_entry_active(seeded_client: FlaskClient) -> None:
    html = seeded_client.get("/calendar/2024/1").data.decode()
    assert "/calendar/" in _active_hrefs(html)


def test_explorer_entry_is_active_only_for_its_own_zoom(
    seeded_client: FlaskClient,
) -> None:
    active = _active_hrefs(seeded_client.get("/explorer/14/server-side").data.decode())
    assert "/explorer/14/server-side" in active
    assert "/explorer/17/server-side" not in active


def test_square_planner_entry_is_active_only_for_its_own_zoom(
    seeded_client: FlaskClient,
) -> None:
    # The landing route redirects to a concrete square, so the entry has to stay
    # active on the square planner itself.
    response = seeded_client.get("/square-planner/14", follow_redirects=True)
    active = _active_hrefs(response.data.decode())
    assert "/square-planner/14" in active
    assert "/square-planner/17" not in active


def test_settings_sub_pages_activate_the_settings_link(
    seeded_client: FlaskClient,
) -> None:
    html = seeded_client.get("/settings/color-schemes").data.decode()
    assert "/settings/" in _active_hrefs(html)


def test_nothing_is_active_on_the_home_page(seeded_client: FlaskClient) -> None:
    assert not _active_hrefs(seeded_client.get("/").data.decode())


def test_maps_stays_a_dropdown_without_photos(
    seeded_client: FlaskClient,
) -> None:
    # Heatmap and Streets are both always visible, so the group has more than
    # one entry even without photos and does not collapse to a plain link.
    navbar = _navbar(seeded_client.get("/").data.decode())
    assert re.search(r'class="nav-link dropdown-toggle\s*"[^>]*>\s*Maps', navbar)
    assert re.search(r'href="/heatmap/"[^>]*>\s*Heatmap', navbar)
    assert re.search(r'href="/streets/"[^>]*>\s*Streets', navbar)
    assert "Photo Map" not in navbar


def test_maps_becomes_a_dropdown_once_photos_exist(seeded_app: Flask) -> None:
    with seeded_app.app_context():
        activity = DB.session.scalars(sqlalchemy.select(Activity).limit(1)).one()
        DB.session.add(
            Photo(
                filename="Photos/somewhere.jpg",
                time=datetime.datetime(2024, 1, 1, 12, 0),
                latitude=51.5,
                longitude=3.6,
                activity_id=activity.id,
            )
        )
        DB.session.commit()

    navbar = _navbar(seeded_app.test_client().get("/").data.decode())
    assert re.search(r'class="nav-link dropdown-toggle\s*"[^>]*>\s*Maps', navbar)
    assert re.search(r'href="/heatmap/"[^>]*>\s*Heatmap', navbar)
    assert re.search(r'href="/photo/map"[^>]*>\s*Photo Map', navbar)
