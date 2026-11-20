# 🍳 FoodChoice

Application intelligente de recommandation de recettes de cuisine basée sur les ingrédients disponibles, avec suggestions de substitutions et personnalisation selon vos goûts.

---

## 🎯 Fonctionnalités
- **Recherche par ingrédients** : Trouvez quoi cuisiner avec ce qui traîne dans votre réfrigérateur.
- **Substitutions intelligentes** : Vous manque-t-il un ingrédient ? L'application suggère des équivalents culinaires.
- **Personnalisation** : Prise en compte de vos ingrédients favoris ou exclus pour affiner les suggestions.
- **Accessible partout** : Utilisable sur ordinateur et smartphone via une interface web responsive.

---

## 🛠️ Stack Technique
- **Backend** : Python, FastAPI, Pydantic, Uvicorn
- **Base de données** : PostgreSQL / SQLite avec SQLAlchemy
- **Frontend** : HTML5, CSS Natif, JavaScript (ES6 fetch)
- **Déploiement** : Docker, hébergement Cloud

---

## 🚀 Démarrage Rapide

### 1. Activer l'environnement virtuel
```bash
source .venv/bin/activate
```

### 2. Installer les dépendances
```bash
pip install -r backend/requirements.txt
```

### 3. Lancer l'application en local
```bash
uvicorn backend.app.main:app --reload --port 8080
```
L'application est ensuite disponible sur :
- **Interface Web :** [http://localhost:8080](http://localhost:8080)
- **Documentation API interactive (Swagger) :** [http://localhost:8080/docs](http://localhost:8080/docs)
