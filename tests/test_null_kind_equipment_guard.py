import sqlalchemy

from geo_activity_playground.core.config import Config
from geo_activity_playground.core.datamodel import (
    DB,
    DEFAULT_UNKNOWN_NAME,
    Activity,
    Equipment,
    Kind,
)
from geo_activity_playground.webui.app import _migrate_null_activity_fields_to_unknown


def test_migration_replaces_null_kind_and_equipment(app):
    with app.app_context():
        activity = Activity(id=1, name="Legacy Nulls", kind_id=None, equipment_id=None)
        DB.session.add(activity)
        DB.session.commit()

        _migrate_null_activity_fields_to_unknown(Config())

        reloaded = DB.session.get_one(Activity, 1)
        assert reloaded.kind is not None
        assert reloaded.equipment is not None
        assert reloaded.kind.name == DEFAULT_UNKNOWN_NAME
        assert reloaded.equipment.name == DEFAULT_UNKNOWN_NAME


def test_edit_route_maps_null_form_values_to_unknown(client, app):
    with app.app_context():
        ride = Kind(name="Ride")
        bike = Equipment(name="Bike")
        DB.session.add_all([ride, bike])
        DB.session.flush()
        activity = Activity(id=1, name="To Edit", kind_id=ride.id, equipment_id=bike.id)
        DB.session.add(activity)
        DB.session.commit()

    response = client.post(
        "/activity/edit/1",
        data={"name": "To Edit", "kind": "null", "equipment": "null"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        reloaded = DB.session.get_one(Activity, 1)
        assert reloaded.kind is not None
        assert reloaded.equipment is not None
        assert reloaded.kind.name == DEFAULT_UNKNOWN_NAME
        assert reloaded.equipment.name == DEFAULT_UNKNOWN_NAME
        unknown_kinds = DB.session.scalars(
            sqlalchemy.select(Kind).where(Kind.name == DEFAULT_UNKNOWN_NAME)
        ).all()
        unknown_equipments = DB.session.scalars(
            sqlalchemy.select(Equipment).where(Equipment.name == DEFAULT_UNKNOWN_NAME)
        ).all()
        assert len(unknown_kinds) == 1
        assert len(unknown_equipments) == 1
