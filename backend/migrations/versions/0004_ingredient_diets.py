"""add ingredient_diets table with is_vegetarian and is_vegan

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

NON_VEGETARIAN_CATEGORIES = {"viande", "poisson"}
NON_VEGAN_CATEGORIES = {"viande", "poisson", "produit laitier", "fromage"}
NON_VEGETARIAN_ALLERGENS = {"poissons", "crustaces", "mollusques"}
NON_VEGAN_ALLERGENS = {"lait", "oeufs", "poissons", "crustaces", "mollusques"}


def _backfill_ingredient_diets() -> None:
    bind = op.get_bind()

    # Map ingredient_id -> set of allergen slugs
    allergen_rows = bind.execute(
        sa.text(
            "SELECT ia.ingredient_id, a.name "
            "FROM ingredient_allergens ia "
            "JOIN allergens a ON a.id = ia.allergen_id"
        )
    ).fetchall()
    allergens_by_ing: dict[int, set[str]] = {}
    for ing_id, allergen_name in allergen_rows:
        allergens_by_ing.setdefault(ing_id, set()).add(allergen_name)

    ingredients = bind.execute(sa.text("SELECT id, category FROM ingredients")).fetchall()
    if not ingredients:
        return

    rows = []
    for ing_id, raw_category in ingredients:
        cat = (raw_category or "").strip().lower()
        ing_allergens = allergens_by_ing.get(ing_id, set())
        is_vegetarian = (cat not in NON_VEGETARIAN_CATEGORIES) and not (ing_allergens & NON_VEGETARIAN_ALLERGENS)
        is_vegan = (cat not in NON_VEGAN_CATEGORIES) and not (ing_allergens & NON_VEGAN_ALLERGENS)
        rows.append(
            {
                "ingredient_id": ing_id,
                "is_vegetarian": is_vegetarian,
                "is_vegan": is_vegan,
            }
        )

    ingredient_diets = sa.table(
        "ingredient_diets",
        sa.column("ingredient_id", sa.Integer),
        sa.column("is_vegetarian", sa.Boolean),
        sa.column("is_vegan", sa.Boolean),
    )
    op.bulk_insert(ingredient_diets, rows)


def upgrade() -> None:
    op.create_table(
        'ingredient_diets',
        sa.Column('ingredient_id', sa.Integer(), nullable=False),
        sa.Column('is_vegetarian', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_vegan', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('ingredient_id'),
    )
    _backfill_ingredient_diets()


def downgrade() -> None:
    op.drop_table('ingredient_diets')
