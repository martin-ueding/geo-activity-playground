import sqlalchemy

from ...core.activities import ActivityRepository
from ...core.config import ConfigAccessor
from ...core.datamodel import DB
from ...core.sources import ActivitySource
from .importer import import_from_hammerhead_api
from .model import HammerheadAuth


class HammerheadActivitySource(ActivitySource):
    @property
    def source(self) -> str:
        return "hammerhead"

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:  # noqa: ARG002
        auth = DB.session.scalar(sqlalchemy.select(HammerheadAuth).limit(1))
        return auth is not None and bool(auth.client_code)

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        repository: ActivityRepository,
        begin: str | None = None,
        end: str | None = None,
    ) -> None:
        import_from_hammerhead_api(
            config_accessor.activity_import(),
            repository,
            begin,
            end,
            source=self.source,
        )
