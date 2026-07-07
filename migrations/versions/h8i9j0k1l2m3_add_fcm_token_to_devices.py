"""add fcm_token to devices

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('devices', sa.Column('fcm_token', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('devices', 'fcm_token')
