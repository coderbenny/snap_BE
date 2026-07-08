"""Add subscriptions table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a1
Create Date: 2026-06-22

"""

import sqlalchemy as sa
from alembic import op

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('tier', sa.Enum('pro', 'pro_ai', 'team', name='sub_tier'), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'past_due', 'cancelled', 'trialing', name='sub_status'),
            nullable=False,
            server_default='active',
        ),
        sa.Column('paystack_customer_code', sa.String(100), nullable=True),
        sa.Column('paystack_sub_code', sa.String(100), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])
    op.create_index('ix_subscriptions_paystack_sub_code', 'subscriptions', ['paystack_sub_code'])


def downgrade():
    op.drop_index('ix_subscriptions_paystack_sub_code', table_name='subscriptions')
    op.drop_index('ix_subscriptions_user_id', table_name='subscriptions')
    op.drop_table('subscriptions')
