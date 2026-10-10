"""Split Strava export activities into their own source.

The Strava export and the Strava API both used the source name `strava`, so they
shared one ingest version stamp. Activities from the export are recognized by their
file under `Strava Export` and move to `strava_export`; the API keeps `strava`.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "746b73795e2e"
down_revision: str | None = "ca66a2c1fb21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IN_EXPORT = "(path LIKE 'Strava Export/%' OR path LIKE 'Strava Export\\%')"


def upgrade() -> None:
    op.execute(
        "UPDATE activities SET source = 'strava_export' "
        f"WHERE (source = 'strava' OR source IS NULL) AND {IN_EXPORT}"
    )
    op.execute(
        "UPDATE import_exclusions SET source = 'strava_export' "
        f"WHERE source = 'strava' AND {IN_EXPORT}"
    )
    _update_priorities(
        lambda priorities: priorities.setdefault(
            "strava_export", priorities.get("strava", 20)
        )
    )


def downgrade() -> None:
    op.execute("UPDATE activities SET source = 'strava' WHERE source = 'strava_export'")
    op.execute(
        "DELETE FROM import_exclusions WHERE source = 'strava_export' AND upstream_id IN "
        "(SELECT upstream_id FROM import_exclusions WHERE source = 'strava')"
    )
    op.execute(
        "UPDATE import_exclusions SET source = 'strava' WHERE source = 'strava_export'"
    )
    _update_priorities(lambda priorities: priorities.pop("strava_export", None))


def _update_priorities(change) -> None:
    bind = op.get_bind()
    for config_id, raw in bind.execute(
        sa.text("SELECT id, duplicate_source_priorities FROM config_activity_import")
    ).all():
        priorities = json.loads(raw) if isinstance(raw, str) else dict(raw)
        change(priorities)
        bind.execute(
            sa.text(
                "UPDATE config_activity_import SET duplicate_source_priorities = :p "
                "WHERE id = :id"
            ),
            {"p": json.dumps(priorities), "id": config_id},
        )
