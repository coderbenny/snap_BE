"""Add app_version to devices, make last_seen_at non-nullable

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-27

"""

import sqlalchemy as sa
from alembic import op

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE devices SET last_seen_at = created_at WHERE last_seen_at IS NULL")

    with op.batch_alter_table('devices') as batch_op:
        batch_op.add_column(sa.Column('app_version', sa.String(20), nullable=True))
        batch_op.alter_column('last_seen_at', nullable=False)


def downgrade():
    with op.batch_alter_table('devices') as batch_op:
        batch_op.alter_column('last_seen_at', nullable=True)
        batch_op.drop_column('app_version')
