import pathlib

from ...core.config import ConfigAccessor
from ...core.datamodel import Activity
from ...core.sources import ActivitySource
from . import api_importer, checkout_importer
from .api_importer import import_from_strava_api, reingest_strava_activity
from .checkout_importer import import_from_strava_checkout, reingest_checkout_activity
from .upstream import API_SOURCE, EXPORT_SOURCE


class StravaCheckoutActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return EXPORT_SOURCE

    @property
    def ingest_version(self) -> int:
        return checkout_importer.INGEST_VERSION

    def reingest(self, activity: Activity, config_accessor: ConfigAccessor) -> bool:
        return reingest_checkout_activity(activity, config_accessor.activity_import())

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
        return API_SOURCE

    @property
    def ingest_version(self) -> int:
        return api_importer.INGEST_VERSION

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
