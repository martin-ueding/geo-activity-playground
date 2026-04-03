from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5be2d6a88e1"
down_revision: str | None = "9d455cc64bcf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cluster_history_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("zoom", sa.Integer(), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=True),
        sa.Column("tile_x", sa.Integer(), nullable=False),
        sa.Column("tile_y", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name="cluster_history_event_activity_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zoom", "event_index", name="uq_cluster_history_events"),
    )
    with op.batch_alter_table("cluster_history_events", schema=None) as batch_op:
        batch_op.create_index(
            "idx_cluster_history_events_zoom_index",
            ["zoom", "event_index"],
            unique=False,
        )
        batch_op.create_index(
            "idx_cluster_history_events_zoom_time",
            ["zoom", "time"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_cluster_history_events_activity_id"),
            ["activity_id"],
            unique=False,
        )

    op.create_table(
        "cluster_history_checkpoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("zoom", sa.Integer(), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=True),
        sa.Column("max_cluster_size", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "zoom", "event_index", name="uq_cluster_history_checkpoints"
        ),
    )
    with op.batch_alter_table("cluster_history_checkpoints", schema=None) as batch_op:
        batch_op.create_index(
            "idx_cluster_history_checkpoints_zoom_index",
            ["zoom", "event_index"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("cluster_history_checkpoints", schema=None) as batch_op:
        batch_op.drop_index("idx_cluster_history_checkpoints_zoom_index")
    op.drop_table("cluster_history_checkpoints")

    with op.batch_alter_table("cluster_history_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cluster_history_events_activity_id"))
        batch_op.drop_index("idx_cluster_history_events_zoom_time")
        batch_op.drop_index("idx_cluster_history_events_zoom_index")
    op.drop_table("cluster_history_events")
