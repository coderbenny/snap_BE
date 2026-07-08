"""Add teams, team_members, shared_snippets, team_invites tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-22

"""

import sqlalchemy as sa
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'teams',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('owner_id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_teams_owner_id', 'teams', ['owner_id'])

    op.create_table(
        'team_members',
        sa.Column('team_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('role', sa.Enum('owner', 'member', name='member_role'), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('team_id', 'user_id'),
    )

    op.create_table(
        'shared_snippets',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('team_id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('ciphertext', sa.Text(), nullable=False),
        sa.Column('iv', sa.String(24), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_shared_snippets_team_synced', 'shared_snippets', ['team_id', 'synced_at']
    )

    op.create_table(
        'team_invites',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('team_id', sa.String(36), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_team_invites_email', 'team_invites', ['email'])
    op.create_index('ix_team_invites_token_hash', 'team_invites', ['token_hash'])


def downgrade():
    op.drop_index('ix_team_invites_token_hash', table_name='team_invites')
    op.drop_index('ix_team_invites_email', table_name='team_invites')
    op.drop_table('team_invites')
    op.drop_index('ix_shared_snippets_team_synced', table_name='shared_snippets')
    op.drop_table('shared_snippets')
    op.drop_table('team_members')
    sa.Enum(name='member_role').drop(op.get_bind(), checkfirst=True)
    op.drop_index('ix_teams_owner_id', table_name='teams')
    op.drop_table('teams')
