import pathlib

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.sources import ActivitySource
from .api_importer import import_from_strava_api
from .checkout_importer import import_from_strava_checkout


class StravaCheckoutActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return "strava"

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:  # noqa: ARG002
        return pathlib.Path("Strava Export").exists()

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        repository: ActivityRepository,  # noqa: ARG002
        begin: str | None = None,  # noqa: ARG002
        end: str | None = None,  # noqa: ARG002
    ) -> None:
        import_from_strava_checkout(
            config_accessor.activity_import(),
            source=self.source,
        )


class StravaApiActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return "strava"

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:
        return config_accessor.strava().strava_client_code is not None

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        repository: ActivityRepository,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        import_from_strava_api(
            config_accessor,
            repository,
            begin,
            end,
            source=self.source,
        )


class StravaActivitySource(ActivitySource):
    def __init__(self) -> None:
        self._sources = [
            StravaCheckoutActivitySource(),
            StravaApiActivitySource(),
        ]

    @property
    def source(self) -> str:
        return "strava"

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:
        return any(source.is_enabled(config_accessor) for source in self._sources)

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        repository: ActivityRepository,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        for source in self._sources:
            if source.is_enabled(config_accessor):
                source.import_activities(config_accessor, repository, begin, end)
