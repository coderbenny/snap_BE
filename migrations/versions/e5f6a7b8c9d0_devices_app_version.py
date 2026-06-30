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
    conn = op.get_bind()

    op.execute(sa.text(
        "UPDATE devices SET last_seen_at = created_at WHERE last_seen_at IS NULL"
    ))

    # Guard against duplicate column from a previously partial run
    col_exists = conn.execute(sa.text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'devices' AND COLUMN_NAME = 'app_version'"
    )).scalar()

    if not col_exists:
        op.add_column('devices', sa.Column('app_version', sa.String(20), nullable=True))

    with op.batch_alter_table('devices') as batch_op:
        batch_op.alter_column('last_seen_at',
                              existing_type=sa.DateTime(),
                              nullable=False)


def downgrade():
    with op.batch_alter_table('devices') as batch_op:
        batch_op.alter_column('last_seen_at',
                              existing_type=sa.DateTime(),
                              nullable=True)
        batch_op.drop_column('app_version')
