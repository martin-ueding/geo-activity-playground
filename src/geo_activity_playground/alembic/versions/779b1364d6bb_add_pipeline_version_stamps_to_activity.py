import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "779b1364d6bb"
down_revision: str | None = "7526d4b8323c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The pipeline versions as of this revision. Existing activities are stamped as
# current rather than stale: they were produced by this very code, and stamping them
# behind would re-read every source file on the next scan. Catching up with improved
# code is what a later version bump is for.
INGEST_VERSION = 1
ENRICHMENT_VERSIONS = {
    "enrichment_set_timezone": 1,
    "enrichment_normalize_time": 1,
    "enrichment_rename_altitude": 1,
    "enrichment_compute_tile_xy": 1,
    "enrichment_elevation_gain": 1,
    "enrichment_add_calories": 1,
    "enrichment_distance": 1,
    "enrichment_moving_time": 1,
    "enrichment_copy_latlon": 1,
}


def upgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ingest_version",
                sa.Integer(),
                nullable=False,
                server_default=str(INGEST_VERSION),
            )
        )
        batch_op.add_column(
            sa.Column(
                "enrichment_versions",
                sa.JSON(),
                nullable=False,
                server_default=json.dumps(ENRICHMENT_VERSIONS),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_column("enrichment_versions")
        batch_op.drop_column("ingest_version")
