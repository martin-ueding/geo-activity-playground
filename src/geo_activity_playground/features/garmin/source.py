from ...core.config import ConfigAccessor
from ...core.datamodel import Activity
from ...core.sources import ActivitySource
from .importer import (
    INGEST_VERSION,
    SOURCE,
    import_from_garmin,
    reingest_garmin_activity,
)
from .model import get_garmin_auth


class GarminActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return SOURCE

    @property
    def ingest_version(self) -> int:
        return INGEST_VERSION

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:  # noqa: ARG002
        return bool(get_garmin_auth().token_json)

    def reingest(self, activity: Activity, config_accessor: ConfigAccessor) -> bool:
        return reingest_garmin_activity(activity, config_accessor.activity_import())

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        import_from_garmin(
            config_accessor.activity_import(), begin, end, source=self.source
        )
