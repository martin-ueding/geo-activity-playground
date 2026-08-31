import abc
import pathlib
import typing

from .config import ConfigAccessor

if typing.TYPE_CHECKING:
    from .datamodel import Activity


class ActivitySource(abc.ABC):
    """Abstract base class for an upstream source of activities."""

    @property
    @abc.abstractmethod
    def source(self) -> str:
        """Stable, unique source name stored on imported activities."""
        ...

    @property
    def ingest_version(self) -> int:
        """The version of the code that turns this source's artifact into an activity.

        Raise it when the extraction changes, and every activity of this source whose
        stamp lags behind is ingested again on the next scan. Sources that kept their
        raw artifact can do that offline; the others report the activity as stale.
        """
        return 1

    def reingest(
        self,
        activity: "Activity",  # noqa: ARG002
        config_accessor: ConfigAccessor,  # noqa: ARG002
    ) -> bool:
        """Run the ingest stage again from the kept artifact.

        Returns False when the artifact is gone, which leaves the activity stale
        rather than reaching out to a remote API behind the user's back.
        """
        return False

    @abc.abstractmethod
    def is_enabled(self, config_accessor: ConfigAccessor) -> bool:
        """Whether this source is currently configured and should run."""
        ...

    @abc.abstractmethod
    def import_activities(
        self,
        config_accessor: ConfigAccessor,
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

    @property
    def ingest_version(self) -> int:
        from ..features.directory_import.importer import INGEST_VERSION

        return INGEST_VERSION

    def import_activities(
        self,
        config_accessor: ConfigAccessor,
        begin: str | None = None,  # noqa: ARG002
        end: str | None = None,  # noqa: ARG002
    ) -> None:
        from ..features.directory_import.importer import import_from_directory

        import_from_directory(
            config_accessor.activity_import(),
            source=self.source,
        )

    def reingest(self, activity: "Activity", config_accessor: ConfigAccessor) -> bool:
        from ..features.directory_import.importer import reingest_activity

        return reingest_activity(activity, config_accessor.activity_import())
