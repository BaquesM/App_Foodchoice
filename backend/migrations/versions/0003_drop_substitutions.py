"""drop substitutions table (feature abandoned)

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('substitutions')


def downgrade() -> None:
    op.create_table('substitutions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('original_ingredient_id', sa.Integer(), nullable=False),
    sa.Column('substitute_ingredient_id', sa.Integer(), nullable=False),
    sa.Column('ratio', sa.Float(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['original_ingredient_id'], ['ingredients.id'], ),
    sa.ForeignKeyConstraint(['substitute_ingredient_id'], ['ingredients.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('substitutions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_substitutions_id'), ['id'], unique=False)
