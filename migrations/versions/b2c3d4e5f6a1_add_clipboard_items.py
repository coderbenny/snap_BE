"""Add clipboard_items table

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-21

"""

import sqlalchemy as sa
from alembic import op

revision = 'b2c3d4e5f6a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'clipboard_items',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('device_id', sa.String(36), nullable=True),
        sa.Column('ciphertext', sa.Text(), nullable=False),
        sa.Column('iv', sa.String(24), nullable=False),
        sa.Column(
            'content_type',
            sa.Enum('text', 'image', 'url', 'file', name='content_type'),
            nullable=False,
            server_default='text',
        ),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('client_created_at', sa.BigInteger(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_clipboard_items_user_synced', 'clipboard_items', ['user_id', 'synced_at']
    )
    op.create_index(
        'ix_clipboard_items_user_deleted', 'clipboard_items', ['user_id', 'deleted_at']
    )


def downgrade():
    op.drop_index('ix_clipboard_items_user_deleted', table_name='clipboard_items')
    op.drop_index('ix_clipboard_items_user_synced', table_name='clipboard_items')
    op.drop_table('clipboard_items')
