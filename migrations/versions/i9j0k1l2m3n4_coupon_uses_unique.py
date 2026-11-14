"""unique (coupon_id, user_id) on coupon_uses

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-11-14

"""
from alembic import op

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    # Earlier races may have left duplicate (coupon, user) rows, which would
    # make the constraint fail. Keep the oldest row of each pair. The nested
    # derived table is required by MySQL (it cannot select from the table it
    # is deleting from otherwise).
    op.execute(
        """
        DELETE FROM coupon_uses
        WHERE id NOT IN (
            SELECT keep_id FROM (
                SELECT MIN(id) AS keep_id
                FROM coupon_uses
                GROUP BY coupon_id, user_id
            ) AS keepers
        )
        """
    )
    with op.batch_alter_table('coupon_uses') as batch:
        batch.create_unique_constraint(
            'uq_coupon_uses_coupon_user', ['coupon_id', 'user_id']
        )


def downgrade():
    with op.batch_alter_table('coupon_uses') as batch:
        batch.drop_constraint('uq_coupon_uses_coupon_user', type_='unique')
