import sqlalchemy

from ...core.config import ConfigAccessor
from ...core.datamodel import DB, Activity
from ...core.sources import ActivitySource
from .importer import (
    INGEST_VERSION,
    import_from_hammerhead_api,
    reingest_hammerhead_activity,
)
from .model import HammerheadAuth


class HammerheadActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return "hammerhead"

    @property
    def ingest_version(self) -> int:
        return INGEST_VERSION

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:  # noqa: ARG002
        auth = DB.session.scalar(sqlalchemy.select(HammerheadAuth).limit(1))
        return auth is not None and bool(auth.client_code)

    def reingest(self, activity: Activity, config_accessor: ConfigAccessor) -> bool:
        return reingest_hammerhead_activity(activity, config_accessor.activity_import())

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        import_from_hammerhead_api(
            config_accessor.activity_import(),
            begin,
            end,
            source=self.source,
        )
