"""add diet flags and allergen links to household_profiles

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('household_profiles', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_vegetarian', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column('is_vegan', sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        'profile_allergens',
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('allergen_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['household_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['allergen_id'], ['allergens.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('profile_id', 'allergen_id'),
    )


def downgrade() -> None:
    op.drop_table('profile_allergens')
    with op.batch_alter_table('household_profiles', schema=None) as batch_op:
        batch_op.drop_column('is_vegan')
        batch_op.drop_column('is_vegetarian')
