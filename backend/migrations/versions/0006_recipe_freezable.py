"""add is_freezable boolean column to recipes

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_freezable', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_column('is_freezable')
