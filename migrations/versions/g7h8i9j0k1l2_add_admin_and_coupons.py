"""Add is_admin/is_active to users, add coupons and coupon_uses tables

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-01

"""

import sqlalchemy as sa
from alembic import op

revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # ── Users: admin flag + active flag ──────────────────────────────────────
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'))

    # ── Coupons ───────────────────────────────────────────────────────────────
    op.create_table(
        'coupons',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column(
            'discount_type',
            sa.Enum('percentage', 'fixed_usd_cents', name='discount_type'),
            nullable=False,
        ),
        sa.Column('discount_value', sa.Integer(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('current_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'tier_restriction',
            sa.Enum('pro', 'pro_ai', 'team', name='coupon_tier'),
            nullable=True,
        ),
        sa.Column('valid_from', sa.DateTime(), nullable=False),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_coupons_code', 'coupons', ['code'])

    # ── Coupon uses ───────────────────────────────────────────────────────────
    op.create_table(
        'coupon_uses',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('coupon_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column(
            'tier',
            sa.Enum('pro', 'pro_ai', 'team', name='coupon_use_tier'),
            nullable=True,
        ),
        sa.Column('used_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['coupon_id'], ['coupons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_coupon_uses_coupon_id', 'coupon_uses', ['coupon_id'])
    op.create_index('ix_coupon_uses_user_id', 'coupon_uses', ['user_id'])


def downgrade():
    op.drop_index('ix_coupon_uses_user_id', table_name='coupon_uses')
    op.drop_index('ix_coupon_uses_coupon_id', table_name='coupon_uses')
    op.drop_table('coupon_uses')

    op.drop_index('ix_coupons_code', table_name='coupons')
    op.drop_table('coupons')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('is_admin')
