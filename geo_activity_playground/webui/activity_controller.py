import functools

from geo_activity_playground.core.activities import ActivityRepository


class ActivityController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    @functools.lru_cache()
    def render_activity(self, id: int) -> dict:
        activity = self._repository.get_activity_by_id(int(id))
        return {"activity": activity}
