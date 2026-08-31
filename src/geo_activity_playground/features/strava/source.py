import pathlib

from ...core.config import ConfigAccessor
from ...core.datamodel import Activity
from ...core.sources import ActivitySource
from .api_importer import (
    INGEST_VERSION,
    import_from_strava_api,
    reingest_strava_activity,
)
from .checkout_importer import import_from_strava_checkout


class StravaCheckoutActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return "strava"

    def reingest(self, activity: Activity, config_accessor: ConfigAccessor) -> bool:
        # A checkout activity keeps its file under `Activities`, so it can be read
        # again the same way a directory activity is.
        from ..directory_import.importer import reingest_activity

        return reingest_activity(activity, config_accessor.activity_import())

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:  # noqa: ARG002
        return pathlib.Path("Strava Export").exists()

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
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

    @property
    def ingest_version(self) -> int:
        return INGEST_VERSION

    def reingest(self, activity: Activity, config_accessor: ConfigAccessor) -> bool:
        return reingest_strava_activity(activity, config_accessor.activity_import())

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:
        return config_accessor.strava().strava_client_code is not None

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        import_from_strava_api(
            config_accessor,
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

    @property
    def ingest_version(self) -> int:
        return max(source.ingest_version for source in self._sources)

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:
        return any(source.is_enabled(config_accessor) for source in self._sources)

    def reingest(self, activity: Activity, config_accessor: ConfigAccessor) -> bool:
        return any(
            source.reingest(activity, config_accessor) for source in self._sources
        )

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        for source in self._sources:
            if source.is_enabled(config_accessor):
                source.import_activities(config_accessor, begin, end)
