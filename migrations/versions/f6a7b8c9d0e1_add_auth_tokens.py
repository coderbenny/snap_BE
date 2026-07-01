"""Add password_reset_tokens, email_verification_tokens, subscription.expiry_warning_sent_at

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-30

"""

import sqlalchemy as sa
from alembic import op

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()

    if 'password_reset_tokens' not in existing_tables:
        op.create_table(
            'password_reset_tokens',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token_hash'),
        )
        op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
        op.create_index('ix_password_reset_tokens_token_hash', 'password_reset_tokens', ['token_hash'])

    if 'email_verification_tokens' not in existing_tables:
        op.create_table(
            'email_verification_tokens',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token_hash'),
        )
        op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'])
        op.create_index('ix_email_verification_tokens_token_hash', 'email_verification_tokens', ['token_hash'])

    existing_sub_cols = [c['name'] for c in sa.inspect(conn).get_columns('subscriptions')]
    if 'expiry_warning_sent_at' not in existing_sub_cols:
        op.add_column('subscriptions', sa.Column('expiry_warning_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.drop_column('expiry_warning_sent_at')

    op.drop_index('ix_email_verification_tokens_token_hash', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')

    op.drop_index('ix_password_reset_tokens_token_hash', table_name='password_reset_tokens')
    op.drop_index('ix_password_reset_tokens_user_id', table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
