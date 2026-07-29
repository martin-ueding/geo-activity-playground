import abc
import pathlib

from .activities import ActivityRepository
from .config import ConfigAccessor


class ActivitySource(abc.ABC):
    """Abstract base class for an upstream source of activities."""

    @property
    @abc.abstractmethod
    def source(self) -> str:
        """Stable, unique source name stored on imported activities."""
        ...

    @abc.abstractmethod
    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:
        """Whether this source is currently configured and should run."""
        ...

    @abc.abstractmethod
    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        repository: ActivityRepository,
        begin: str | None = None,  # noqa: ARG002
        end: str | None = None,  # noqa: ARG002
    ) -> None:
        """Import activities from this source."""
        ...


class DirectoryImportSource(ActivitySource):
    @property
    def source(self) -> str:
        return "directory"

    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:  # noqa: ARG002
        return pathlib.Path("Activities").exists()

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        repository: ActivityRepository,
        begin: str | None = None,  # noqa: ARG002
        end: str | None = None,  # noqa: ARG002
    ) -> None:
        from ..features.directory_import.importer import import_from_directory

        import_from_directory(
            repository,
            config_accessor.activity_import(),
            config_accessor.ui(),
            source=self.source,
        )
