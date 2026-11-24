"""Interactive CLI to add ingredients (category, seasonality, allergens) to the database.

Usage (from the project root):
    .venv/bin/python scripts/add_ingredient.py

Target database:
  - local    -> sqlite:///./foodchoice.db
  - supabase -> SUPABASE_DATABASE_URL (or DATABASE_URL) read from the git-ignored .env file
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CATEGORIES = [
    "légume", "fruit", "féculent", "protéine", "viande", "poisson",
    "produit laitier", "matière grasse", "herbe/épice", "autre",
]
MONTH_NAMES = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def ask(prompt: str) -> str:
    return input(prompt).strip()


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    answer = ask(f"{prompt} ({'O/n' if default else 'o/N'}) : ").lower()
    return default if not answer else answer in ("o", "oui", "y", "yes")


def parse_months(raw: str) -> list[int]:
    """'all' -> 1..12 ; '9, 10, 11' -> [9, 10, 11]. Raises ValueError on invalid input."""
    raw = raw.strip().lower()
    if raw in ("all", "tous", "toute l'année"):
        return list(range(1, 13))
    months = sorted({int(x) for x in raw.replace(";", ",").replace(" ", ",").split(",") if x})
    if not months or any(m < 1 or m > 12 for m in months):
        raise ValueError("Les mois doivent être compris entre 1 et 12.")
    return months


def parse_choices(raw: str, size: int) -> list[int]:
    """'1, 3' -> [0, 2] (0-based indexes). Empty or '0' -> []. Raises ValueError on invalid input."""
    raw = raw.strip()
    if raw in ("", "0"):
        return []
    picks = sorted({int(x) for x in raw.replace(" ", ",").split(",") if x})
    if any(p < 1 or p > size for p in picks):
        raise ValueError(f"Choisissez des numéros entre 1 et {size}.")
    return [p - 1 for p in picks]


def choose_database_url() -> str:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print("Base cible :\n  [1] Locale (SQLite)\n  [2] Supabase (production)")
    while True:
        choice = ask("Choix [1-2] : ")
        if choice == "1":
            return "sqlite:///./foodchoice.db"
        if choice == "2":
            url = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")
            if not url:
                sys.exit("SUPABASE_DATABASE_URL est absent du fichier .env (voir .env.example).")
            if not ask_yes_no("⚠️  Vous allez écrire dans la base de PRODUCTION. Continuer", default=False):
                sys.exit("Annulé.")
            return url


def add_ingredient(db, name: str, category: str, months: list[int], allergen_names: list[str]):
    """Create the ingredient with its seasonality and allergens. Returns None if the name already exists."""
    from backend.app.models.recipe import Allergen, Ingredient

    if db.query(Ingredient).filter(Ingredient.name.ilike(name)).first():
        return None
    allergens = db.query(Allergen).filter(Allergen.name.in_(allergen_names)).all() if allergen_names else []
    ingredient = Ingredient(name=name, category=category, available_months=months)
    ingredient.allergen_links = allergens
    db.add(ingredient)
    db.commit()
    return ingredient


def main():
    os.environ["DATABASE_URL"] = choose_database_url()

    # Imported only now: the session module reads DATABASE_URL at import time
    from backend.app.db.init_db import run_migrations
    from backend.app.db.session import SessionLocal
    from backend.app.models.recipe import Allergen, Ingredient

    print("\nVérification du schéma de la base (migrations)...")
    run_migrations()

    db = SessionLocal()
    try:
        all_allergens = db.query(Allergen).order_by(Allergen.id).all()
        while True:
            print("\n=== AJOUT D'UN INGRÉDIENT ===")
            name = ask("Nom de l'ingrédient : ").capitalize()
            if not name:
                print("Le nom est obligatoire.")
                continue
            if db.query(Ingredient).filter(Ingredient.name.ilike(name)).first():
                print(f"'{name}' existe déjà, abandon.")
                continue

            print("\nCatégorie :")
            for i, c in enumerate(CATEGORIES, 1):
                print(f"  [{i}] {c}")
            while True:
                try:
                    idx = parse_choices(ask(f"Choix [1-{len(CATEGORIES)}] : "), len(CATEGORIES))
                    if len(idx) == 1:
                        category = CATEGORIES[idx[0]]
                        break
                    print("Choisissez exactement une catégorie.")
                except ValueError as e:
                    print(e)

            print("\nMois de disponibilité (1 = janvier ... 12 = décembre)")
            while True:
                try:
                    months = parse_months(ask("'all' ou liste séparée par des virgules (ex: 9,10,11) : "))
                    break
                except ValueError as e:
                    print(e)

            print("\nAllergènes présents :")
            print("  [0] Aucun")
            for i, a in enumerate(all_allergens, 1):
                print(f"  [{i}] {a.label}")
            while True:
                try:
                    picks = parse_choices(ask("Choix (séparés par des virgules, ex: 8) : "), len(all_allergens))
                    allergen_names = [all_allergens[p].name for p in picks]
                    break
                except ValueError as e:
                    print(e)

            print("\n" + "-" * 50)
            print("Récapitulatif :")
            print(f"  - Ingrédient : {name}")
            print(f"  - Catégorie  : {category}")
            print(f"  - Mois       : {', '.join(MONTH_NAMES[m - 1] for m in months)}")
            print(f"  - Allergènes : {', '.join(a.label for a in all_allergens if a.name in allergen_names) or 'aucun'}")
            if ask_yes_no("Enregistrer dans la base ?"):
                add_ingredient(db, name, category, months, allergen_names)
                print("✅ Ingrédient enregistré.")
            else:
                print("Annulé.")

            if not ask_yes_no("\nAjouter un autre ingrédient ?"):
                break
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nInterrompu.")
