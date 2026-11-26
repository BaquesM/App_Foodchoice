"""add recipe_allergens association table

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recipe_allergens',
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('allergen_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['allergen_id'], ['allergens.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('recipe_id', 'allergen_id'),
    )


def downgrade() -> None:
    op.drop_table('recipe_allergens')
