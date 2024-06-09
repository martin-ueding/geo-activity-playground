import logging

from ..core.activities import ActivityRepository

logger = logging.getLogger(__name__)


class SearchController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    def render_search_results(self, name: str) -> dict:
        logger.info(f"Searching for {name=}")
        activities = []
        for _, row in self._repository.meta.iterrows():
            if name in row["name"]:
                activities.append(
                    {
                        "name": row["name"],
                        "start": row["start"].isoformat(),
                        "kind": row["kind"],
                        "distance_km": row["distance_km"],
                        "elapsed_time": row["elapsed_time"],
                    }
                )

        return {"activities": activities}
