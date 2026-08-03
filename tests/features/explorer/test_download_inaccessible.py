from flask import Flask
from flask.testing import FlaskClient

from geo_activity_playground.core.datamodel import DB
from geo_activity_playground.core.tiles import get_tile_upper_left_lat_lon
from geo_activity_playground.features.explorer.model import InaccessibleTile


def test_download_inaccessible_geojson(app: Flask, client: FlaskClient) -> None:
    zoom = 14
    tile_x, tile_y = 100, 100
    with app.app_context():
        DB.session.add(InaccessibleTile(zoom=zoom, tile_x=tile_x, tile_y=tile_y))  # pyright: ignore
        DB.session.commit()

    north, west = get_tile_upper_left_lat_lon(tile_x, tile_y, zoom)
    south, east = get_tile_upper_left_lat_lon(tile_x + 1, tile_y + 1, zoom)

    response = client.get(
        f"/explorer/{zoom}/{north}/{east}/{south}/{west}/inaccessible.geojson"
    )

    assert response.status_code == 200
    assert response.json["features"]
