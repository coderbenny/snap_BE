"""add file_transfer_addon to subscriptions

Revision ID: fc6f45df22b8
Revises: g7h8i9j0k1l2
Create Date: 2026-07-07 10:10:19.189140

"""
import sqlalchemy as sa
from alembic import op

revision = 'fc6f45df22b8'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.add_column(
            sa.Column('file_transfer_addon', sa.Boolean(), nullable=False, server_default='0')
        )


def downgrade():
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.drop_column('file_transfer_addon')
