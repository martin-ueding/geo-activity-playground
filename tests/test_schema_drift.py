"""The migrations must produce the schema that the models declare.

Tests build their schema with ``DB.create_all()`` while production upgrades an
existing database with Alembic. Without this test the two could drift apart
unnoticed, and it also catches a model change for which no migration was
generated.
"""

import pathlib

import sqlalchemy
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from geo_activity_playground.core.datamodel import Base
from geo_activity_playground.webui import (
    app as _app,  # noqa: F401  (registers all models)
)

REPO_ROOT = pathlib.Path(__file__).parent.parent


def test_migrations_match_models(tmp_path: pathlib.Path) -> None:
    database_path = tmp_path / "database.sqlite"
    config = Config(REPO_ROOT / "alembic.ini")
    config.set_main_option(
        "script_location",
        str(REPO_ROOT / "src" / "geo_activity_playground" / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = sqlalchemy.create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "render_as_batch": True}
        )
        diff = compare_metadata(context, Base.metadata)
    engine.dispose()

    assert diff == [], f"Models and migrations disagree: {diff}"
