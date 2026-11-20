# Guide du Projet & Instructions d'Assistance (CLAUDE.md)

Ce document sert de mémoire et de cadre de référence pour le projet **FoodChoice**.

---

## 1. Contexte & Profil de la Développeuse
* **Développeuse :** Marion (Docteure en sismologie).
* **Compétences initiales :** Solide bagage en Python scientifique, Bash, Matlab, modélisation et analyse de données. Débutante en développement web.
* **Objectif professionnel :** Monter en compétences sur des technologies logicielles standard de l'industrie (marché R&D / Backend / Data Engineering à Sophia Antipolis).
* **Localisation :** Sophia Antipolis, France.

---

## 2. Règles Pédagogiques Impératives
1. **Pas à pas strict (Pair Programming) :** Avancer **une seule étape à la fois**.
2. **Explication avant action :** Toujours expliquer le *pourquoi* et le *comment* avant d'écrire ou modifier du code.
3. **Validation explicite :** Ne jamais enchaîner plusieurs étapes sans l'accord ou la validation de Marion.
4. **Faire le pont avec ses acquis :** Relier les concepts du web (HTTP, API, bases de données) à ce qu'elle connaît déjà (fonctions Python, scripts Bash, matrices/données).
5. **Langue du code :** Tous les commentaires de code, docstrings et noms de variables/fonctions doivent être rédigés en **anglais** (standard de l'industrie / Sophia Antipolis).
6. **Documentation :** Toute la documentation doit être rédigée au format Markdown (`.md`).

---

## 3. Stack Technique Retenue
* **Langage Backend :** Python 3.10+
* **Framework API :** FastAPI + Pydantic (validation des schémas de données)
* **Serveur ASGI :** Uvicorn
* **Base de données & ORM :** PostgreSQL (Cloud/Prod) / SQLite (développement local) via SQLAlchemy
* **Frontend :** HTML5 sémantique, CSS Natif (variables CSS, Flexbox/Grid, responsive), JavaScript moderne (ES6+, `fetch` asynchrone)
* **DevOps & Déploiement :** Git/GitHub, Docker, hébergement Cloud (ex: Render) accessible sur mobile et PC
* **Tests :** pytest, httpx

---

## 4. Objectifs Fonctionnels de FoodChoice
1. **Gestion des ingrédients :** Saisie des ingrédients disponibles dans le frigo/placard.
2. **Moteur de recettes :** Correspondance intelligente (score de matching selon les ingrédients possédés).
3. **Moteur de substitution :** Proposer des alternatives si un ingrédient manque (ex: yaourt grec à la place de crème fraîche).
4. **Apprentissage des goûts (Feedback loop) :** Prise en compte des ingrédients aimés/rejetés pour pondérer les recommandations.

---

## 5. Feuille de Route (Roadmap & Backlog)
* **En cours (Étape 1) :** Gestion visuelle des profils du foyer (ajout de convives) et interface de notation des goûts (-2 à +2).
* **Prochaine étape (Étape 4) :** Dockerisation & Déploiement Cloud (Dockerfile, hébergement Render/Fly.io).
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
```
