import geojson

from ..core.activities import ActivityRepository


class LocationsController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    def render_index(self) -> dict:
        activity_endpoints = []
        for activity in self._repository.iter_activities():
            activity_endpoints.append(
                (activity["start_latitude"], activity["start_longitude"])
            )
            activity_endpoints.append(
                (activity["end_latitude"], activity["end_longitude"])
            )

        activity_endpoints_geojson = geojson.dumps(
            geojson.FeatureCollection(
                [
                    geojson.Feature(geometry=geojson.Point((longitude, latitude)))
                    for latitude, longitude in activity_endpoints
                ]
            )
        )
        return {"activity_endpoints_geojson": activity_endpoints_geojson}
