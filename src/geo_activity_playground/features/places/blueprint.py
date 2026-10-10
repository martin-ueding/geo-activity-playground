import collections

import sqlalchemy
from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ...core.datamodel import DB, Activity
from ...core.meta_search import activity_ids_for_search
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes
from ...webui.search_context import search_context
from .discovery import propose_places
from .matching import rematch_all_stays
from .model import PLACE_RADIUS_M, Place
from .visits import Leg, PlaceId, count_legs


def make_places_blueprint(authenticator: Authenticator, flasher: Flasher) -> Blueprint:
    blueprint = Blueprint("places", __name__, template_folder="templates")

    @blueprint.route("/")
    def index() -> ResponseReturnValue:
        primitives, search_vars = search_context(authenticator)
        legs = count_legs(activity_ids_for_search(primitives))
        places = _load_places()
        return render_template(
            "places/index.html.j2",
            places=places,
            matrix_keys=_matrix_keys(legs),
            names={place.id: place.name for place in places},
            legs=legs,
            map_places={
                place.id: {
                    "name": place.name,
                    "latitude": place.latitude,
                    "longitude": place.longitude,
                    "round_trips": legs[place.id, place.id],
                }
                for place in places
            },
            map_edges=[
                {"origin": origin, "destination": destination, "count": count}
                for (origin, destination), count in legs.items()
                if origin is not None
                and destination is not None
                and origin != destination
            ],
            **search_vars,
        )

    @blueprint.route("/edit")
    def edit() -> ResponseReturnValue:
        latest_start = DB.session.execute(
            sqlalchemy.select(Activity.start_latitude, Activity.start_longitude)
            .where(Activity.start_latitude.is_not(None))
            .order_by(Activity.start.desc().nulls_last())
            .limit(1)
        ).first()
        return render_template(
            "places/edit.html.j2",
            places=[
                {
                    "id": place.id,
                    "name": place.name,
                    "latitude": place.latitude,
                    "longitude": place.longitude,
                    "update_url": url_for(".update", id=place.id),
                    "delete_url": url_for(".delete", id=place.id),
                }
                for place in _load_places()
            ],
            proposals=[vars(proposal) for proposal in propose_places()],
            radius_m=PLACE_RADIUS_M,
            fallback_center=list(latest_start) if latest_start else [20.0, 0.0],
        )

    @blueprint.route("/new", methods=["POST"])
    @needs_authentication(authenticator)
    def new() -> ResponseReturnValue:
        if (form := _place_form()) is None:
            return redirect(url_for(".edit"))
        place = Place(**form)
        DB.session.add(place)
        rematch_all_stays()
        flasher.flash_message(
            _("Created place “%(name)s”.", name=place.name), FlashTypes.SUCCESS
        )
        return redirect(url_for(".edit"))

    @blueprint.route("/<int:id>/update", methods=["POST"])
    @needs_authentication(authenticator)
    def update(id: int) -> ResponseReturnValue:
        place = DB.session.get_one(Place, id)
        if (form := _place_form()) is None:
            return redirect(url_for(".edit"))
        for key, value in form.items():
            setattr(place, key, value)
        rematch_all_stays()
        flasher.flash_message(
            _("Updated place “%(name)s”.", name=place.name), FlashTypes.SUCCESS
        )
        return redirect(url_for(".edit"))

    @blueprint.route("/<int:id>/delete", methods=["POST"])
    @needs_authentication(authenticator)
    def delete(id: int) -> ResponseReturnValue:
        place = DB.session.get_one(Place, id)
        name = place.name
        for stay in place.stays:
            stay.place_id = None
        DB.session.delete(place)
        rematch_all_stays()
        flasher.flash_message(
            _("Deleted place “%(name)s”.", name=name), FlashTypes.SUCCESS
        )
        return redirect(url_for(".edit"))

    def _place_form() -> dict | None:
        name = request.form.get("name", "").strip()
        latitude = request.form.get("latitude", type=float)
        longitude = request.form.get("longitude", type=float)
        if not name or latitude is None or longitude is None:
            flasher.flash_message(
                _("A place needs a name and a position."), FlashTypes.WARNING
            )
            return None
        return {"name": name, "latitude": latitude, "longitude": longitude}

    return blueprint


def _load_places() -> list[Place]:
    return list(DB.session.scalars(sqlalchemy.select(Place).order_by(Place.name)))


def _matrix_keys(legs: collections.Counter[Leg]) -> list[PlaceId]:
    """Places that occur in a leg, the busiest first and unknown last."""
    totals: collections.Counter[PlaceId] = collections.Counter()
    for (origin, destination), count in legs.items():
        totals[origin] += count
        totals[destination] += count
    return sorted(totals, key=lambda id: (id is None, -totals[id]))
