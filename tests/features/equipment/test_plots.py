import datetime as dt
import json

from flask import Flask

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.datamodel import DB, Activity, Equipment, Kind
from geo_activity_playground.features.equipment.blueprint import _equipment_plots


def _add_activity(kind: Kind, equipment: Equipment, start: dt.datetime | None) -> None:
    DB.session.add(
        Activity(
            name=(
                f"{equipment.name} {start:%Y}" if start else f"{equipment.name} undated"
            ),
            start=start,
            iana_timezone="UTC",
            distance_km=10.0,
            elevation_gain=0.0,
            moving_time=dt.timedelta(minutes=30),
            elapsed_time=dt.timedelta(minutes=30),
            kind_id=kind.id,
            equipment_id=equipment.id,
        )
    )


def test_yearly_distance_plot_shows_only_own_kinds(app: Flask) -> None:
    with app.test_request_context():
        ride = Kind(name="Ride")
        run = Kind(name="Run")
        bike = Equipment(name="Bike")
        shoes = Equipment(name="Shoes")
        DB.session.add_all([ride, run, bike, shoes])
        DB.session.flush()
        _add_activity(ride, bike, dt.datetime(2024, 5, 1, 10))
        _add_activity(ride, bike, dt.datetime(2025, 5, 1, 10))
        _add_activity(ride, bike, None)
        _add_activity(run, shoes, dt.datetime(2025, 5, 1, 10))
        DB.session.commit()

        spec = json.loads(
            _equipment_plots(ConfigAccessor(), "Bike")["yearly_distance_plot"]
        )

    legend = spec["legends"][0]
    assert legend["values"] == ["Ride"]

    # The scale itself keeps every kind, so the colors stay stable across plots.
    color_scale = next(scale for scale in spec["scales"] if scale["name"] == "color")
    assert color_scale["domain"] == ["Ride", "Run"]

    # The year has to reach the browser as a plain string, otherwise the tooltip
    # has to reconstruct it from a timestamp and shows `undefined`. Activities
    # without a start time keep their distance in a bar of their own.
    rows = spec["data"][0]["values"]
    assert {row["year"] for row in rows} == {"2024", "2025", "Unknown"}
    assert sum(row["distance_km"] for row in rows) == 30.0
