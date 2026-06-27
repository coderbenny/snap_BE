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
    op.add_column('devices', sa.Column('app_version', sa.String(20), nullable=True))

    # Back-fill last_seen_at for any existing rows that have NULL, then tighten
    op.execute("UPDATE devices SET last_seen_at = created_at WHERE last_seen_at IS NULL")
    op.alter_column('devices', 'last_seen_at', nullable=False)


def downgrade():
    op.alter_column('devices', 'last_seen_at', nullable=True)
    op.drop_column('devices', 'app_version')
