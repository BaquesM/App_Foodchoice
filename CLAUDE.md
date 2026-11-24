# Guide du Projet FoodChoice (CLAUDE.md)

Ce document sert de mémoire technique pour le projet **FoodChoice**.

---

## 1. Préférences de travail
Le profil de Marion et les règles de travail (pas à pas, validation avant action, exemples concrets, langues, Git) sont dans `~/.claude/CLAUDE.md`. Ce fichier ne décrit que le projet **FoodChoice**.

---

## 2. Stack Technique Retenue
* **Langage Backend :** Python 3.10+
* **Framework API :** FastAPI + Pydantic (validation des schémas de données)
* **Serveur ASGI :** Uvicorn
* **Base de données & ORM :** PostgreSQL (Supabase, prod) / SQLite (développement local) via SQLAlchemy
* **Migrations :** Alembic (`backend/alembic.ini`, `backend/migrations/versions/`), appliquées automatiquement au démarrage du serveur par `init_db()` (donc à chaque déploiement Render)
* **Frontend :** HTML5 sémantique, CSS Natif (variables CSS, Flexbox/Grid, responsive), JavaScript moderne (ES6+, `fetch` asynchrone)
* **DevOps & Déploiement :** Git/GitHub, Docker, hébergement Cloud (ex: Render) accessible sur mobile et PC
* **Tests :** pytest, httpx (base SQLite temporaire isolée, construite via les migrations : voir `backend/tests/conftest.py`)

---

## 3. Objectifs Fonctionnels de FoodChoice
1. **Gestion des ingrédients :** Saisie des ingrédients disponibles dans le frigo/placard.
2. **Moteur de recettes :** Correspondance intelligente (score de matching selon les ingrédients possédés).
3. **Saisonnalité & allergènes :** Chaque ingrédient a ses mois de disponibilité et une liste d'allergènes (14 allergènes officiels UE).
4. **Apprentissage des goûts (Feedback loop) :** Prise en compte des ingrédients aimés/rejetés pour pondérer les recommandations.

> [!NOTE]
> Le moteur de substitution a été **abandonné** (table `substitutions` supprimée par la migration `0003`). Un ingrédient est `available` ou `missing`. Un veto (note -2) d'un convive n'exclut pas la recette : il affiche une bannière « X déteste Y » et la fait passer après les recettes sans veto.

---

## 4. Modèle de Données (ingrédients)
```
ingredients (id, name, category, needs_season_review)
   1..1  ingredient_seasons (ingredient_id PK/FK, jan … dec : 12 booléens)
   0..n  ingredient_allergens (ingredient_id, allergen_id)  ->  allergens (id, name, label)
```
* L'API expose toujours `available_months: [6, 7, 8]` et `allergens: ["lait"]` (conversion faite par les propriétés du modèle `Ingredient`).
* `ingredient_seasons` et `ingredient_allergens` se vident automatiquement quand on supprime un ingrédient (`ON DELETE CASCADE`). `recipe_ingredients` et `user_ingredient_preferences` **bloquent** la suppression tant qu'elles le référencent.
* Les ids ne sont jamais recalculés : les trous de numérotation sont normaux.
* Le seed de `init_db.py` ne s'exécute que si aucun compte n'existe (jamais sur Supabase).

---

## 5. Feuille de Route (Roadmap & Backlog)
* **Réalisé :** profils du foyer et notation des goûts (-2 à +2) ; Dockerisation et déploiement (Render + Supabase) ; migrations Alembic ; saisonnalité en booléens et allergènes ; script d'ajout d'ingrédients.
* **À faire :** renseigner les allergènes et corriger les catégories des ingrédients existants sur Supabase (en cours, à la main) ; filtrer les recettes selon les allergènes des convives.
* **Gardé de côté pour plus tard :**
  * **Option 2 :** Générateur de liste de courses (export des ingrédients manquants ajustés aux portions).
  * **Option 3 :** Vue détaillée « Mode Cuisine » (pas à pas avec minuteurs et ingrédients barrables).

---

## 6. Commandes Utiles (Cheatsheet)
```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Lancer le serveur en mode développement (rechargement automatique)
uvicorn backend.app.main:app --reload --port 8080

# Lancer la suite de tests
pytest backend/tests

# Ajouter un ingrédient (catégorie, mois, allergènes) en local ou sur Supabase
python scripts/add_ingredient.py

# Migrations (depuis la racine du projet)
alembic -c backend/alembic.ini upgrade head                              # appliquer
alembic -c backend/alembic.ini revision --autogenerate -m "description"  # générer (à relire !)
```
Pour viser Supabase avec le script, mettre `SUPABASE_DATABASE_URL` dans `.env` (ignoré par git, voir `.env.example`).
