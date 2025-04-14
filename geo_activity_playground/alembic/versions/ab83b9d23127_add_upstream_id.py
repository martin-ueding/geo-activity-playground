from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ab83b9d23127"
down_revision: Union[str, None] = "b03491c593f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("upstream_id", sa.String(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_column("upstream_id")

    # ### end Alembic commands ###
