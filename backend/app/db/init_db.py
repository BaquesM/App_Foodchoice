"""Database initialization and test seed data injection."""
import sys
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from backend.app.db.session import engine, SessionLocal, Base
from backend.app.models.recipe import (
    UserAccount,
    HouseholdProfile,
    Ingredient,
    Allergen,
    Recipe,
    RecipeIngredient,
    RecipeShare,
    Substitution,
    UserIngredientPreference,
)

MIGRATIONS_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
BASELINE_REVISION = "0001"


def _alembic_config() -> Config:
    cfg = Config(str(MIGRATIONS_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_INI.parent / "migrations"))
    return cfg


def _patch_legacy_columns():
    """
    Databases created before Alembic may miss a few columns that were once added by hand.
    Add them so the schema matches the baseline revision before it gets stamped.
    """
    insp = inspect(engine)
    legacy_columns = {
        "ingredients": {"needs_season_review": "BOOLEAN DEFAULT FALSE"},
        "recipes": {"parent_recipe_id": "INTEGER REFERENCES recipes(id)"},
        "user_accounts": {"email": "VARCHAR(150)", "supabase_uid": "VARCHAR(100)"},
    }
    with engine.begin() as conn:
        for table, columns in legacy_columns.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def run_migrations():
    """Apply pending Alembic migrations (creates tables, adds columns, migrates data)."""
    insp = inspect(engine)
    # Database predating Alembic: bring it to the baseline schema, then mark it as such
    if insp.has_table("ingredients") and not insp.has_table("alembic_version"):
        _patch_legacy_columns()
        command.stamp(_alembic_config(), BASELINE_REVISION)
    command.upgrade(_alembic_config(), "head")


def init_db(reset: bool = False):
    """
    Migrate the schema to the latest revision and seed initial sample data.
    If reset=True, existing tables are dropped and recreated.
    """
    if reset:
        Base.metadata.drop_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    run_migrations()

    db = SessionLocal()
    try:
        # If accounts already exist, ensure default test emails are populated and return
        if not reset and db.query(UserAccount).first():
            m = db.query(UserAccount).filter_by(username="marion").first()
            if m and not m.email:
                m.email = "marion@test.fr"
            l = db.query(UserAccount).filter_by(username="lisa").first()
            if l and not l.email:
                l.email = "lisa@test.fr"
            o = db.query(UserAccount).filter_by(username="odile").first()
            if o and not o.email:
                o.email = "odile@test.fr"
            db.commit()
            return

        # 1. Accounts
        acc_marion = UserAccount(username="marion", display_name="Marion", email="marion@test.fr")
        acc_lisa = UserAccount(username="lisa", display_name="Lisa", email="lisa@test.fr")
        acc_odile = UserAccount(username="odile", display_name="Odile", email="odile@test.fr")
        db.add_all([acc_marion, acc_lisa, acc_odile])
        db.flush()

        # 2. Household profiles (Dining guests)
        p_marion = HouseholdProfile(account_id=acc_marion.id, name="Marion")
        p_thomas = HouseholdProfile(account_id=acc_marion.id, name="Thomas")

        p_lisa = HouseholdProfile(account_id=acc_lisa.id, name="Lisa")
        p_lucas = HouseholdProfile(account_id=acc_lisa.id, name="Lucas")

        p_odile = HouseholdProfile(account_id=acc_odile.id, name="Odile")

        db.add_all([p_marion, p_thomas, p_lisa, p_lucas, p_odile])
        db.flush()

        # 3. Base ingredients
        oeufs = Ingredient(name="Oeuf", category="protéine", available_months=list(range(1, 13)))
        beurre = Ingredient(name="Beurre", category="matière grasse", available_months=list(range(1, 13)))
        huile_olive = Ingredient(name="Huile d'olive", category="matière grasse", available_months=list(range(1, 13)))
        ciboulette = Ingredient(name="Ciboulette", category="herbe/épice", available_months=[4, 5, 6, 7, 8, 9, 10])
        persil = Ingredient(name="Persil", category="herbe/épice", available_months=list(range(1, 13)))
        pates = Ingredient(name="Pâtes", category="féculent", available_months=list(range(1, 13)))
        lardons = Ingredient(name="Lardons", category="viande", available_months=list(range(1, 13)))
        parmesan = Ingredient(name="Parmesan", category="produit laitier", available_months=list(range(1, 13)))
        tomate = Ingredient(name="Tomate", category="légume", available_months=[6, 7, 8, 9, 10])
        mozzarella = Ingredient(name="Mozzarella", category="produit laitier", available_months=list(range(1, 13)))
        courgette = Ingredient(name="Courgette", category="légume", available_months=[5, 6, 7, 8, 9, 10])
        oignon = Ingredient(name="Oignon", category="légume", available_months=list(range(1, 13)))

        # Allergens (reference rows are inserted by migration 0002)
        allergen_by_name = {a.name: a for a in db.query(Allergen).all()}
        for ingredient, names in [
            (oeufs, ["oeufs"]), (beurre, ["lait"]), (pates, ["gluten"]),
            (parmesan, ["lait"]), (mozzarella, ["lait"]),
        ]:
            ingredient.allergen_links = [allergen_by_name[n] for n in names if n in allergen_by_name]

        db.add_all([
            oeufs, beurre, huile_olive, ciboulette, persil, pates,
            lardons, parmesan, tomate, mozzarella, courgette, oignon
        ])
        db.flush()

        # 4. Substitutions
        sub1 = Substitution(original_ingredient_id=beurre.id, substitute_ingredient_id=huile_olive.id, ratio=0.8, note="Pour la cuisson à la poêle")
        sub2 = Substitution(original_ingredient_id=ciboulette.id, substitute_ingredient_id=persil.id, ratio=1.0, note="Apporte une fraîcheur similaire")
        db.add_all([sub1, sub2])

        # 5. Recipes with Visibility & Ownership
        # Recipe 1: Herb Omelet - Marion's private recipe
        r1 = Recipe(
            account_id=acc_marion.id,
            title="Omelette aux fines herbes",
            instructions="Battre les oeufs avec sel et poivre. Chauffer le beurre dans une poêle. Verser les oeufs, parsemer de ciboulette ciselée et plier l'omelette.",
            prep_time_minutes=5,
            cook_time_minutes=5,
            base_servings=2,
            visibility="private",
            share_token="omelette-secret-token",
        )
        db.add(r1)
        db.flush()

        db.add_all([
            RecipeIngredient(recipe_id=r1.id, ingredient_id=oeufs.id, quantity=4, unit="pièce", importance=3),
            RecipeIngredient(recipe_id=r1.id, ingredient_id=beurre.id, quantity=15, unit="g", importance=2),
            RecipeIngredient(recipe_id=r1.id, ingredient_id=ciboulette.id, quantity=10, unit="g", importance=1),
        ])

        # Option B share: Marion shares r1 with Lisa
        share_marion_to_lisa = RecipeShare(recipe_id=r1.id, shared_with_account_id=acc_lisa.id)
        db.add(share_marion_to_lisa)

        # Recipe 2: Pasta Carbonara - Marion's PUBLIC recipe (Option A: accessible to everyone, including guests)
        r2 = Recipe(
            account_id=acc_marion.id,
            title="Pâtes Carbonara",
            instructions="Cuire les pâtes al dente. Dorer les lardons à sec. Mélanger les oeufs battus avec le parmesan. Hors du feu, mélanger pâtes, lardons et crème d'oeuf/parmesan.",
            prep_time_minutes=10,
            cook_time_minutes=10,
            base_servings=2,
            visibility="public",
            share_token="carbo-public-token",
        )
        db.add(r2)
        db.flush()

        db.add_all([
            RecipeIngredient(recipe_id=r2.id, ingredient_id=pates.id, quantity=200, unit="g", importance=3),
            RecipeIngredient(recipe_id=r2.id, ingredient_id=lardons.id, quantity=100, unit="g", importance=3),
            RecipeIngredient(recipe_id=r2.id, ingredient_id=oeufs.id, quantity=2, unit="pièce", importance=3),
            RecipeIngredient(recipe_id=r2.id, ingredient_id=parmesan.id, quantity=40, unit="g", importance=2),
        ])

        # Recipe 3: Tomato & Mozzarella Salad - Lisa's PRIVATE recipe, shared SPECIFICALLY with Marion (Option B)
        r3 = Recipe(
            account_id=acc_lisa.id,
            title="Salade Tomate Mozzarella",
            instructions="Couper les tomates et la mozzarella en rondelles régulières. Disposer en alternant. Arroser d'un filet d'huile d'olive, saler et poivrer.",
            prep_time_minutes=10,
            cook_time_minutes=0,
            base_servings=2,
            visibility="private",
            share_token="salade-lisa-token",
        )
        db.add(r3)
        db.flush()

        db.add_all([
            RecipeIngredient(recipe_id=r3.id, ingredient_id=tomate.id, quantity=3, unit="pièce", importance=3),
            RecipeIngredient(recipe_id=r3.id, ingredient_id=mozzarella.id, quantity=125, unit="g", importance=3),
            RecipeIngredient(recipe_id=r3.id, ingredient_id=huile_olive.id, quantity=15, unit="ml", importance=2),
        ])

        # Option B share: Lisa shares r3 with Marion's account
        share_lisa_to_marion = RecipeShare(recipe_id=r3.id, shared_with_account_id=acc_marion.id)
        db.add(share_lisa_to_marion)

        # Recipe 4: Odile's PUBLIC recipe - Ratatouille provençale (Option A test)
        r4 = Recipe(
            account_id=acc_odile.id,
            title="Ratatouille d'Odile",
            instructions="Couper courgettes, tomates et oignons en dés. Faire revenir les oignons dans l'huile d'olive, puis ajouter les courgettes et tomates. Laisser mijoter 35 min et parsemer de persil.",
            prep_time_minutes=20,
            cook_time_minutes=35,
            base_servings=4,
            visibility="public",
            share_token="ratatouille-odile-token",
        )
        db.add(r4)
        db.flush()

        db.add_all([
            RecipeIngredient(recipe_id=r4.id, ingredient_id=courgette.id, quantity=2, unit="pièce", importance=3),
            RecipeIngredient(recipe_id=r4.id, ingredient_id=tomate.id, quantity=3, unit="pièce", importance=3),
            RecipeIngredient(recipe_id=r4.id, ingredient_id=oignon.id, quantity=2, unit="pièce", importance=2),
            RecipeIngredient(recipe_id=r4.id, ingredient_id=huile_olive.id, quantity=30, unit="ml", importance=2),
            RecipeIngredient(recipe_id=r4.id, ingredient_id=persil.id, quantity=10, unit="g", importance=1),
        ])

        # Recipe 5: Lisa's PUBLIC recipe - Poêlée campagnarde aux oeufs (Option A test with eggs)
        r5 = Recipe(
            account_id=acc_lisa.id,
            title="Poêlée campagnarde aux oeufs",
            instructions="Faire dorer les lardons et l'oignon émincé à la poêle. Casser les oeufs directement dessus, saler, poivrer et laisser cuire jusqu'à ce que les blancs soient pris.",
            prep_time_minutes=5,
            cook_time_minutes=10,
            base_servings=2,
            visibility="public",
            share_token="poelee-lisa-token",
        )
        db.add(r5)
        db.flush()

        db.add_all([
            RecipeIngredient(recipe_id=r5.id, ingredient_id=oeufs.id, quantity=4, unit="pièce", importance=3),
            RecipeIngredient(recipe_id=r5.id, ingredient_id=lardons.id, quantity=150, unit="g", importance=3),
            RecipeIngredient(recipe_id=r5.id, ingredient_id=oignon.id, quantity=1, unit="pièce", importance=2),
            RecipeIngredient(recipe_id=r5.id, ingredient_id=huile_olive.id, quantity=15, unit="ml", importance=1),
        ])

        # 6. Household preferences (isolated per profile)
        db.add_all([
            # Marion's household
            UserIngredientPreference(profile_id=p_marion.id, ingredient_id=mozzarella.id, rating=2),
            UserIngredientPreference(profile_id=p_marion.id, ingredient_id=ciboulette.id, rating=-1),
            UserIngredientPreference(profile_id=p_thomas.id, ingredient_id=lardons.id, rating=2),
            UserIngredientPreference(profile_id=p_thomas.id, ingredient_id=tomate.id, rating=-2),

            # Lisa's household (separate opinions!)
            UserIngredientPreference(profile_id=p_lisa.id, ingredient_id=courgette.id, rating=2),
            UserIngredientPreference(profile_id=p_lucas.id, ingredient_id=oignon.id, rating=-2),
        ])

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    reset_requested = "--reset" in sys.argv
    init_db(reset=reset_requested)
    print("Database initialized successfully!" + (" (reset performed)" if reset_requested else ""))
