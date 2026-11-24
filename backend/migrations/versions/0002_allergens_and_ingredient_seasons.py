"""allergens and ingredient seasons

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24 10:52:56.731336
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

MONTH_COLUMNS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

# The 14 major allergens regulated in the EU: (slug, display label)
EU_ALLERGENS = [
    ("gluten", "Gluten"),
    ("crustaces", "Crustacés"),
    ("oeufs", "Œufs"),
    ("poissons", "Poissons"),
    ("arachides", "Arachides"),
    ("soja", "Soja"),
    ("lait", "Lait / Lactose"),
    ("fruits_a_coque", "Fruits à coque"),
    ("celeri", "Céleri"),
    ("moutarde", "Moutarde"),
    ("sesame", "Graines de sésame"),
    ("sulfites", "Sulfites"),
    ("lupin", "Lupin"),
    ("mollusques", "Mollusques"),
]


def _seed_allergens() -> None:
    allergens = sa.table("allergens", sa.column("name", sa.String), sa.column("label", sa.String))
    op.bulk_insert(allergens, [{"name": n, "label": l} for n, l in EU_ALLERGENS])


def _migrate_months_to_seasons() -> None:
    """Convert the old JSON string column (e.g. "[6, 7, 8]") into 12 booleans per ingredient."""
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, available_months FROM ingredients")).fetchall()
    seasons = sa.table(
        "ingredient_seasons",
        sa.column("ingredient_id", sa.Integer),
        *[sa.column(c, sa.Boolean) for c in MONTH_COLUMNS],
    )
    data = []
    for ingredient_id, raw in rows:
        try:
            months = set(json.loads(raw)) if raw else set(range(1, 13))
        except Exception:
            months = set(range(1, 13))
        row = {"ingredient_id": ingredient_id}
        row.update({c: (i in months) for i, c in enumerate(MONTH_COLUMNS, start=1)})
        data.append(row)
    if data:
        op.bulk_insert(seasons, data)



def upgrade() -> None:
    op.create_table('allergens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('allergens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_allergens_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_allergens_name'), ['name'], unique=True)

    op.create_table('ingredient_allergens',
    sa.Column('ingredient_id', sa.Integer(), nullable=False),
    sa.Column('allergen_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['allergen_id'], ['allergens.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ingredient_id', 'allergen_id')
    )
    op.create_table('ingredient_seasons',
    sa.Column('ingredient_id', sa.Integer(), nullable=False),
    sa.Column('jan', sa.Boolean(), nullable=False),
    sa.Column('feb', sa.Boolean(), nullable=False),
    sa.Column('mar', sa.Boolean(), nullable=False),
    sa.Column('apr', sa.Boolean(), nullable=False),
    sa.Column('may', sa.Boolean(), nullable=False),
    sa.Column('jun', sa.Boolean(), nullable=False),
    sa.Column('jul', sa.Boolean(), nullable=False),
    sa.Column('aug', sa.Boolean(), nullable=False),
    sa.Column('sep', sa.Boolean(), nullable=False),
    sa.Column('oct', sa.Boolean(), nullable=False),
    sa.Column('nov', sa.Boolean(), nullable=False),
    sa.Column('dec', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ingredient_id')
    )
    _seed_allergens()
    _migrate_months_to_seasons()

    with op.batch_alter_table('ingredients', schema=None) as batch_op:
        batch_op.drop_column('available_months')


def downgrade() -> None:
    with op.batch_alter_table('ingredients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('available_months', sa.VARCHAR(length=100), nullable=True))

    bind = op.get_bind()
    for row in bind.execute(sa.text("SELECT * FROM ingredient_seasons")).mappings().all():
        months = [i for i, c in enumerate(MONTH_COLUMNS, start=1) if row[c]]
        bind.execute(
            sa.text("UPDATE ingredients SET available_months = :m WHERE id = :i"),
            {"m": json.dumps(months), "i": row["ingredient_id"]},
        )

    op.drop_table('ingredient_seasons')
    op.drop_table('ingredient_allergens')
    with op.batch_alter_table('allergens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_allergens_name'))
        batch_op.drop_index(batch_op.f('ix_allergens_id'))

    op.drop_table('allergens')
