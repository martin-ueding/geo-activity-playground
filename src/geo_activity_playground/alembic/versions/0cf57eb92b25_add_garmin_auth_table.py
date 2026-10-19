import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0cf57eb92b25"
down_revision: str | None = "8b48dc908cba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GARMIN_PRIORITY = 15


def upgrade() -> None:
    op.create_table(
        "garmin_auth",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_json", sa.Text(), nullable=True),
        sa.Column("last_activity_date", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Sources that are missing from the priorities rank lowest. Garmin hands out the
    # original device file, so it ranks above the other APIs from the start.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, duplicate_source_priorities FROM config_activity_import")
    ).fetchall()
    for row_id, raw in rows:
        priorities = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        priorities.setdefault("garmin", GARMIN_PRIORITY)
        connection.execute(
            sa.text(
                "UPDATE config_activity_import "
                "SET duplicate_source_priorities = :value WHERE id = :id"
            ),
            {"value": json.dumps(priorities), "id": row_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, duplicate_source_priorities FROM config_activity_import")
    ).fetchall()
    for row_id, raw in rows:
        priorities = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        priorities.pop("garmin", None)
        connection.execute(
            sa.text(
                "UPDATE config_activity_import "
                "SET duplicate_source_priorities = :value WHERE id = :id"
            ),
            {"value": json.dumps(priorities), "id": row_id},
        )

    op.drop_table("garmin_auth")
