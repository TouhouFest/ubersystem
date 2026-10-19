"""Add selling_nsfw and touhou_work_percentage columns to group

Revision ID: b4a7d18e2f09
Revises: 5a0e898174d4
Create Date: 2026-10-11 17:21:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b4a7d18e2f09"
down_revision = "5a0e898174d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "group",
        sa.Column("selling_nsfw", sa.Boolean(), server_default="False", nullable=False),
    )
    op.add_column(
        "group", sa.Column("touhou_work_percentage", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("group", "touhou_work_percentage")
    op.drop_column("group", "selling_nsfw")
