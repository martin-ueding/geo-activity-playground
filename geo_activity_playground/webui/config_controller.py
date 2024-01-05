from geo_activity_playground.core.activities import ActivityRepository


class ConfigController:
    def __init__(self, repository: ActivityRepository) -> None:
        self._repository = repository

    def action_index(self) -> dict:
        return {}

    def action_save(self, form_input) -> dict:
        return {}
