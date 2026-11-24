import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.recipe import Ingredient, Recipe, Substitution, UserAccount, HouseholdProfile, UserIngredientPreference, RecipeUpdateNotification

client = TestClient(app)

def test_health_check():
    """Ensure the /api/health endpoint returns status 200 and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data

def test_home_page():
    """Ensure the root route '/' serves the HTML frontend."""
    response = client.get("/")
    assert response.status_code == 200
    assert "FoodChoice" in response.text

def test_list_ingredients():
    """Ensure /api/ingredients returns a non-empty list of ingredients."""
    response = client.get("/api/ingredients")
    assert response.status_code == 200
    ingredients = response.json()
    assert len(ingredients) > 0
    assert "name" in ingredients[0]
    assert "available_months" in ingredients[0]

def test_list_accounts_and_profiles():
    """Ensure /api/accounts and /api/accounts/{id}/profiles return seeded entities."""
    response = client.get("/api/accounts")
    assert response.status_code == 200
    accounts = response.json()
    names = [a["display_name"] for a in accounts]
    assert "Marion" in names
    assert "Lisa" in names

    marion_acc = next(a for a in accounts if a["username"] == "marion")
    prof_res = client.get(f"/api/accounts/{marion_acc['id']}/profiles")
    assert prof_res.status_code == 200
    profiles = prof_res.json()
    p_names = [p["name"] for p in profiles]
    assert "Marion" in p_names
    assert "Thomas" in p_names

def test_search_recipes_with_account():
    """Ensure /api/recipes/search returns ranked recipes for an account."""
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    ingredients = client.get("/api/ingredients").json()
    oeuf_id = next(i["id"] for i in ingredients if i["name"] == "Oeuf")
    beurre_id = next(i["id"] for i in ingredients if i["name"] == "Beurre")

    payload = {
        "account_id": marion["id"],
        "ingredient_ids": [oeuf_id, beurre_id],
        "target_servings": 2,
        "profile_ids": [],
        "include_public": True,
    }
    response = client.post("/api/recipes/search", json=payload)
    assert response.status_code == 200
    recipes = response.json()
    assert len(recipes) > 0
    assert recipes[0]["title"] == "Omelette aux fines herbes"
    assert recipes[0]["match_score"] > 80.0

def test_create_and_share_recipe():
    """Ensure a user can create a recipe and share it via token (Option C) and with account (Option B)."""
    db = SessionLocal()
    for old in db.query(Recipe).filter_by(title="Courgettes poêlées").all():
        db.delete(old)
    db.commit()

    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    lisa = next(a for a in accounts if a["username"] == "lisa")
    ingredients = client.get("/api/ingredients").json()
    courgette_id = next(i["id"] for i in ingredients if i["name"] == "Courgette")

    new_recipe_payload = {
        "account_id": marion["id"],
        "title": "Courgettes poêlées",
        "instructions": "Laver, couper et poêler.",
        "prep_time_minutes": 5,
        "cook_time_minutes": 10,
        "base_servings": 2,
        "visibility": "private",
        "ingredients": [
            {"ingredient_id": courgette_id, "quantity": 2.0, "unit": "pièce", "importance": 3}
        ]
    }
    create_res = client.post("/api/recipes", json=new_recipe_payload)
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["title"] == "Courgettes poêlées"
    assert "share_token" in created

    # Option C: Direct token access
    token_res = client.get(f"/api/recipes/shared/{created['share_token']}")
    assert token_res.status_code == 200
    assert token_res.json()["title"] == "Courgettes poêlées"

    # Option B: Share with Lisa
    share_res = client.post(f"/api/recipes/{created['recipe_id']}/share", json={"target_account_id": lisa["id"]})
    assert share_res.status_code == 200

    # Clean up
    rec_db = db.query(Recipe).filter_by(id=created["recipe_id"]).first()
    if rec_db:
        db.delete(rec_db)
        db.commit()
    db.close()

def test_preference_submission():
    """Ensure a household profile can record an ingredient rating."""
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    profiles = client.get(f"/api/accounts/{marion['id']}/profiles").json()
    marion_profile = next(p for p in profiles if p["name"] == "Marion")
    ingredients = client.get("/api/ingredients").json()
    courgette_id = next(i["id"] for i in ingredients if i["name"] == "Courgette")

    payload = {
        "profile_id": marion_profile["id"],
        "ingredient_id": courgette_id,
        "rating": 2,
    }
    response = client.post("/api/preferences", json=payload)
    assert response.status_code == 200
    assert "Adoré" in response.json()["message"]

def test_invalid_preference_rating_rejected():
    """Ensure Pydantic rejects rating outside [-2, 2]."""
    payload = {
        "profile_id": 1,
        "ingredient_id": 1,
        "rating": 5,
    }
    response = client.post("/api/preferences", json=payload)
    assert response.status_code == 422


def test_list_public_recipes():
    """Ensure /api/recipes/public returns only public recipes for guests and users."""
    response = client.get("/api/recipes/public")
    assert response.status_code == 200
    recipes = response.json()
    assert len(recipes) > 0
    assert all(r["visibility"] == "public" for r in recipes)
    titles = [r["title"] for r in recipes]
    assert "Pâtes Carbonara" in titles


def test_create_recipe_with_substitution():
    """Ensure proposing a substitution ingredient during recipe creation registers the rule."""
    db = SessionLocal()
    for old in db.query(Recipe).filter_by(title="Gratin de légumes au parmesan").all():
        db.delete(old)
    db.commit()

    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    ingredients = client.get("/api/ingredients").json()
    parmesan_id = next(i["id"] for i in ingredients if i["name"] == "Parmesan")
    mozzarella_id = next(i["id"] for i in ingredients if i["name"] == "Mozzarella")

    payload = {
        "account_id": marion["id"],
        "title": "Gratin de légumes au parmesan",
        "instructions": "Cuire les légumes et gratiner au four avec le fromage.",
        "prep_time_minutes": 10,
        "cook_time_minutes": 25,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {
                "ingredient_id": parmesan_id,
                "quantity": 50.0,
                "unit": "g",
                "importance": 2,
                "substitute_ingredient_id": mozzarella_id,
                "substitute_ratio": 1.2,
                "substitute_note": "Mozzarella râpée si pas de parmesan"
            }
        ]
    }
    res = client.post("/api/recipes", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Gratin de légumes au parmesan"

    # Cleanup
    rec_db = db.query(Recipe).filter_by(id=created["recipe_id"]).first()
    if rec_db:
        db.delete(rec_db)
        db.commit()
    db.close()


def test_create_recipe_with_unknown_substitute_name_and_quantity():
    """Ensure free-text unknown substitute ingredients are automatically created and ratio is computed."""
    db = SessionLocal()
    for old in db.query(Recipe).filter_by(title="Poêlée douce").all():
        db.delete(old)
    db.commit()

    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    ingredients = client.get("/api/ingredients").json()
    courgette_id = next(i["id"] for i in ingredients if i["name"] == "Courgette")

    payload = {
        "account_id": marion["id"],
        "title": "Poêlée douce",
        "instructions": "Mélanger et cuire au four.",
        "prep_time_minutes": 10,
        "cook_time_minutes": 30,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {
                "ingredient_id": courgette_id,
                "quantity": 100.0,
                "unit": "g",
                "importance": 2,
                "substitute_name": "Crème d'avoine",
                "substitute_quantity": 80.0,
                "substitute_ratio": 0.8,
                "substitute_note": "Version végétale sans lactose"
            }
        ]
    }
    res = client.post("/api/recipes", json=payload)
    assert res.status_code == 201
    created = res.json()

    # Verify that 'Crème d'avoine' was created in ingredients catalog
    all_ing = client.get("/api/ingredients").json()
    creme_avoine = next((i for i in all_ing if "avoine" in i["name"].lower()), None)
    assert creme_avoine is not None
    assert creme_avoine["name"] == "Crème d'avoine"

    # Cleanup
    rec_db = db.query(Recipe).filter_by(id=created["recipe_id"]).first()
    if rec_db:
        db.delete(rec_db)
        db.commit()
    db.close()


def test_shared_with_in_recipe_recommendation():
    """Ensure recipes have shared_with list populated with recipient display names."""
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    res = client.get(f"/api/accounts/{marion['id']}/recipes")
    assert res.status_code == 200
    recipes = res.json()
    omelette = next((r for r in recipes if r["title"] == "Omelette aux fines herbes"), None)
    assert omelette is not None
    assert "Lisa" in omelette["shared_with"]


def test_create_and_get_household_profile():
    """Ensure an account can add a dining profile and query its preferences."""
    from backend.app.db.session import SessionLocal
    from backend.app.models.recipe import HouseholdProfile

    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")

    # Clean up Paul if leftover from previous test run
    db = SessionLocal()
    db.query(HouseholdProfile).filter_by(account_id=marion["id"], name="Paul").delete()
    db.commit()
    db.close()

    # Create profile "Paul"
    create_res = client.post(f"/api/accounts/{marion['id']}/profiles", json={"name": "Paul"})
    assert create_res.status_code == 201
    paul = create_res.json()
    assert paul["name"] == "Paul"

    # Reject duplicate profile name
    dup_res = client.post(f"/api/accounts/{marion['id']}/profiles", json={"name": "Paul"})
    assert dup_res.status_code == 400

    # Query preferences (initially empty)
    prefs_res = client.get(f"/api/profiles/{paul['id']}/preferences")
    assert prefs_res.status_code == 200
    assert prefs_res.json() == []

    # Clean up
    db = SessionLocal()
    db.query(HouseholdProfile).filter_by(id=paul["id"]).delete()
    db.commit()
    db.close()


def test_create_recipe_with_new_ingredient_and_category():
    """Ensure an ingredient can be added by name and category (e.g. Saumon / poisson)."""
    from backend.app.db.session import SessionLocal
    from backend.app.models.recipe import Ingredient, Recipe

    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")

    payload = {
        "account_id": marion["id"],
        "title": "Pavé de saumon grillé",
        "instructions": "Cuire le pavé à la poêle 4 minutes de chaque côté.",
        "prep_time_minutes": 5,
        "cook_time_minutes": 8,
        "base_servings": 2,
        "visibility": "private",
        "ingredients": [
            {
                "name": "Saumon frais",
                "category": "poisson",
                "quantity": 250.0,
                "unit": "g",
                "importance": 3
            }
        ]
    }
    res = client.post("/api/recipes", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Pavé de saumon grillé"

    # Verify ingredient in database with category
    all_ing = client.get("/api/ingredients").json()
    saumon = next((i for i in all_ing if i["name"] == "Saumon frais"), None)
    assert saumon is not None
    assert saumon["category"] == "poisson"

    # Clean up test recipe
    db = SessionLocal()
    db.query(Recipe).filter_by(id=created["recipe_id"]).delete()
    db.commit()
    db.close()


def test_create_recipe_with_substitute_unit_and_quantity():
    """Ensure substitute unit and quantity are saved without requiring an explicit ratio."""
    from backend.app.db.session import SessionLocal
    from backend.app.models.recipe import Recipe, Substitution

    db_init = SessionLocal()
    for old in db_init.query(Recipe).filter_by(title="Salade verte vinaigrette").all():
        db_init.delete(old)
    db_init.commit()
    db_init.close()

    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")

    payload = {
        "account_id": marion["id"],
        "title": "Salade verte vinaigrette",
        "instructions": "Laver et assaisonner.",
        "prep_time_minutes": 5,
        "cook_time_minutes": 0,
        "base_servings": 2,
        "visibility": "private",
        "ingredients": [
            {
                "name": "Huile de colza",
                "category": "matière grasse",
                "quantity": 20.0,
                "unit": "ml",
                "importance": 2,
                "substitute_name": "Huile de noix",
                "substitute_quantity": 15.0,
                "substitute_unit": "ml",
                "substitute_note": "Goût plus fruité"
            }
        ]
    }
    res = client.post("/api/recipes", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Salade verte vinaigrette"

    # Check that substitution note contains unit and calculated ratio
    db = SessionLocal()
    sub = (
        db.query(Substitution)
        .join(Substitution.original_ingredient)
        .filter(Substitution.original_ingredient.has(name="Huile de colza"))
        .first()
    )
    assert sub is not None
    assert sub.ratio == pytest.approx(0.75, abs=0.01)
    assert "15.0 ml" in sub.note

    # Clean up test recipe
    db.query(Recipe).filter_by(id=created["recipe_id"]).delete()
    db.commit()
    db.close()


def test_create_new_ingredient_seasonality_and_unknown_warning():
    """Test creating new ingredients with custom season months and 'unknown' season warning."""
    from backend.app.db.session import SessionLocal
    db = SessionLocal()
    # Cleanup any leftovers
    for ing in db.query(Ingredient).filter(Ingredient.name.in_(["Melon de cavaillon", "Fruit exotique mystere"])).all():
        db.delete(ing)  # ORM delete so the seasonality row is removed too
    db.commit()
    db.close()

    payload = {
        "account_id": 1,
        "title": "Salade estivale au melon",
        "instructions": "• Couper le melon.\n• Servir très frais.",
        "prep_time_minutes": 10,
        "cook_time_minutes": 0,
        "base_servings": 2,
        "visibility": "public",
        "ingredients": [
            {
                "name": "Melon de cavaillon",
                "category": "fruit",
                "quantity": 300,
                "unit": "g",
                "importance": 3,
                "available_months": [6, 7, 8, 9],
                "season_unknown": False,
            },
            {
                "name": "Fruit exotique mystere",
                "category": "fruit",
                "quantity": 100,
                "unit": "g",
                "importance": 1,
                "available_months": list(range(1, 13)),
                "season_unknown": True,
            }
        ]
    }
    res = client.post("/api/recipes", json=payload)
    assert res.status_code == 201

    db = SessionLocal()
    melon = db.query(Ingredient).filter_by(name="Melon de cavaillon").first()
    assert melon is not None
    assert melon.available_months == [6, 7, 8, 9]
    assert melon.needs_season_review is False

    mystere = db.query(Ingredient).filter_by(name="Fruit exotique mystere").first()
    assert mystere is not None
    assert mystere.needs_season_review is True

    # Check that admin endpoint returns the flagged ingredient
    admin_res = client.get("/api/admin/pending-season-ingredients")
    assert admin_res.status_code == 200
    pending_list = admin_res.json()
    pending_names = [ing["name"] for ing in pending_list]
    assert "Fruit exotique mystere" in pending_names
    assert "Melon de cavaillon" not in pending_names

    # Cleanup
    created_id = res.json()["recipe_id"]
    rec_to_del = db.query(Recipe).filter_by(id=created_id).first()
    if rec_to_del:
        db.delete(rec_to_del)
    for ing in db.query(Ingredient).filter(Ingredient.name.in_(["Melon de cavaillon", "Fruit exotique mystere"])).all():
        db.delete(ing)  # ORM delete so the seasonality row is removed too
    db.commit()
    db.close()


def test_delete_household_profile():
    """Ensure a household dining profile and their preferences can be deleted."""
    # 1. Create a temporary profile
    create_res = client.post("/api/accounts/1/profiles", json={"name": "TempConvive"})
    assert create_res.status_code == 201
    profile_data = create_res.json()
    profile_id = profile_data["id"]

    # 2. Add an ingredient preference for this profile
    pref_res = client.post("/api/preferences", json={
        "profile_id": profile_id,
        "ingredient_id": 1,
        "rating": -2
    })
    assert pref_res.status_code == 200

    # 3. Delete the profile
    del_res = client.delete(f"/api/profiles/{profile_id}")
    assert del_res.status_code == 200
    assert "supprimé avec succès" in del_res.json()["message"]

    # 4. Verify profile no longer exists
    db = SessionLocal()
    prof_check = db.query(HouseholdProfile).filter_by(id=profile_id).first()
    assert prof_check is None

    # 5. Verify preferences were cascade deleted
    pref_check = db.query(UserIngredientPreference).filter_by(profile_id=profile_id).first()
    assert pref_check is None
    db.close()

    # 6. Verify 404 on deleting non-existent profile
    err_res = client.delete(f"/api/profiles/{profile_id}")
    assert err_res.status_code == 404


def test_alternative_recipe_creation_and_search():
    """
    Ensure user can create an original recipe, then an alternative recipe referencing it.
    Verify that in search and account listings:
    - Original recipe has has_alternatives = True
    - Alternative recipe has is_alternative = True and parent_recipe_title populated
    - Both are returned when searching by shared ingredient (e.g. Chocolat).
    """
    db = SessionLocal()
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")

    # 1. Create original recipe
    orig_payload = {
        "account_id": marion["id"],
        "title": "Gâteau au chocolat classique",
        "instructions": "Faire fondre le chocolat avec le beurre et mélanger avec farine et sucre.",
        "prep_time_minutes": 15,
        "cook_time_minutes": 25,
        "base_servings": 6,
        "visibility": "private",
        "ingredients": [
            {"name": "Chocolat noir pâtissier", "category": "autre", "quantity": 200, "unit": "g", "importance": 3},
            {"name": "Farine de blé", "category": "céréale", "quantity": 100, "unit": "g", "importance": 3},
            {"name": "Sucre roux", "category": "autre", "quantity": 80, "unit": "g", "importance": 2},
            {"name": "Beurre doux", "category": "produit laitier", "quantity": 100, "unit": "g", "importance": 2},
        ]
    }
    orig_res = client.post("/api/recipes", json=orig_payload)
    assert orig_res.status_code == 201
    orig_data = orig_res.json()
    orig_id = orig_data["recipe_id"]
    assert orig_data["is_alternative"] is False

    # 2. Create alternative recipe referencing the original
    alt_payload = {
        "account_id": marion["id"],
        "title": "Gâteau au chocolat et compote",
        "instructions": "Remplacer le beurre par de la compote de pommes.",
        "prep_time_minutes": 15,
        "cook_time_minutes": 25,
        "base_servings": 6,
        "visibility": "private",
        "parent_recipe_id": orig_id,
        "ingredients": [
            {"name": "Chocolat noir pâtissier", "category": "autre", "quantity": 200, "unit": "g", "importance": 3},
            {"name": "Farine de blé", "category": "céréale", "quantity": 100, "unit": "g", "importance": 3},
            {"name": "Sucre roux", "category": "autre", "quantity": 80, "unit": "g", "importance": 2},
            {"name": "Pomme", "category": "fruit", "quantity": 150, "unit": "g", "importance": 2},
        ]
    }
    alt_res = client.post("/api/recipes", json=alt_payload)
    assert alt_res.status_code == 201
    alt_data = alt_res.json()
    alt_id = alt_data["recipe_id"]
    assert alt_data["is_alternative"] is True
    assert alt_data["parent_recipe_id"] == orig_id
    assert alt_data["parent_recipe_title"] == "Gâteau au chocolat classique"

    # 3. Verify in account recipe listing
    account_recipes = client.get(f"/api/accounts/{marion['id']}/recipes").json()
    orig_in_acc = next(r for r in account_recipes if r["recipe_id"] == orig_id)
    alt_in_acc = next(r for r in account_recipes if r["recipe_id"] == alt_id)

    assert orig_in_acc["has_alternatives"] is True
    assert orig_in_acc["is_alternative"] is False
    assert alt_in_acc["is_alternative"] is True
    assert alt_in_acc["parent_recipe_title"] == "Gâteau au chocolat classique"

    # 4. Search by ingredient Chocolat noir pâtissier
    all_ing = client.get("/api/ingredients").json()
    choc = next(i for i in all_ing if "Chocolat" in i["name"])
    search_payload = {
        "account_id": marion["id"],
        "ingredient_ids": [choc["id"]],
        "target_servings": 6,
        "profile_ids": [],
        "min_match_score": 0.0,
        "include_public": True,
    }
    search_res = client.post("/api/recipes/search", json=search_payload)
    assert search_res.status_code == 200
    search_results = search_res.json()

    orig_in_search = next((r for r in search_results if r["recipe_id"] == orig_id), None)
    alt_in_search = next((r for r in search_results if r["recipe_id"] == alt_id), None)

    assert orig_in_search is not None
    assert alt_in_search is not None
    assert orig_in_search["has_alternatives"] is True
    assert orig_in_search["is_alternative"] is False
    assert alt_in_search["is_alternative"] is True
    assert alt_in_search["parent_recipe_title"] == "Gâteau au chocolat classique"

    # Cleanup test data
    rec_alt_db = db.query(Recipe).filter_by(id=alt_id).first()
    if rec_alt_db:
        db.delete(rec_alt_db)
    rec_orig_db = db.query(Recipe).filter_by(id=orig_id).first()
    if rec_orig_db:
        db.delete(rec_orig_db)
    db.commit()
    db.close()


def test_update_recipe_by_author_and_forbidden_for_others():
    """Ensure an author can update their recipe (PUT /api/recipes/{id}) and non-authors receive 403."""
    db = SessionLocal()
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    lisa = next(a for a in accounts if a["username"] == "lisa")

    # Clean pre-existing test recipe
    for old in db.query(Recipe).filter_by(title="Tarte aux pommes rustique").all():
        db.delete(old)
    for old in db.query(Recipe).filter_by(title="Tarte aux pommes dorée").all():
        db.delete(old)
    db.commit()

    # 1. Create initial recipe
    create_payload = {
        "account_id": marion["id"],
        "title": "Tarte aux pommes rustique",
        "instructions": "Éplucher les pommes, disposer sur la pâte et cuire.",
        "prep_time_minutes": 20,
        "cook_time_minutes": 30,
        "base_servings": 6,
        "visibility": "private",
        "ingredients": [
            {"name": "Pomme", "category": "fruit", "quantity": 500, "unit": "g", "importance": 3}
        ]
    }
    c_res = client.post("/api/recipes", json=create_payload)
    assert c_res.status_code == 201
    recipe_id = c_res.json()["recipe_id"]

    # 2. Update as author
    update_payload = {
        "account_id": marion["id"],
        "title": "Tarte aux pommes dorée",
        "instructions": "Éplucher, badigeonner de beurre et cuire au four 35 min.",
        "prep_time_minutes": 25,
        "cook_time_minutes": 35,
        "base_servings": 8,
        "visibility": "public",
        "ingredients": [
            {"name": "Pomme", "category": "fruit", "quantity": 600, "unit": "g", "importance": 3},
            {"name": "Beurre doux", "category": "produit laitier", "quantity": 30, "unit": "g", "importance": 2}
        ]
    }
    u_res = client.put(f"/api/recipes/{recipe_id}", json=update_payload)
    assert u_res.status_code == 200
    u_data = u_res.json()
    assert u_data["title"] == "Tarte aux pommes dorée"
    assert u_data["servings"] == 8
    assert u_data["cook_time_minutes"] == 35
    assert len(u_data["ingredients"]) == 2

    # 3. Attempt update as non-author (Lisa) -> 403 Forbidden
    forbidden_payload = {**update_payload, "account_id": lisa["id"]}
    f_res = client.put(f"/api/recipes/{recipe_id}", json=forbidden_payload)
    assert f_res.status_code == 403

    # Cleanup
    rec_db = db.query(Recipe).filter_by(id=recipe_id).first()
    if rec_db:
        db.delete(rec_db)
        db.commit()
    db.close()


def test_duplicate_recipe_title_rejected():
    """Ensure duplicate recipe titles for the same account are rejected with 400 Bad Request."""
    db = SessionLocal()
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")

    for old in db.query(Recipe).filter_by(title="Soupe à l'oignon gratinée").all():
        db.delete(old)
    db.commit()

    payload = {
        "account_id": marion["id"],
        "title": "Soupe à l'oignon gratinée",
        "instructions": "Caraméliser les oignons, ajouter bouillon et gratiner.",
        "prep_time_minutes": 15,
        "cook_time_minutes": 40,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {"name": "Oignon", "category": "légume", "quantity": 500, "unit": "g", "importance": 3}
        ]
    }
    r1 = client.post("/api/recipes", json=payload)
    assert r1.status_code == 201

    # Attempt to create again with same title (even with leading/trailing spaces or different case)
    dup_payload = {**payload, "title": "  soupe à l'oignon gratinée  "}
    r2 = client.post("/api/recipes", json=dup_payload)
    assert r2.status_code == 400
    assert "exactement les mêmes ingrédients et quantités" in r2.json()["detail"]

    # Cleanup
    rec_db = db.query(Recipe).filter_by(id=r1.json()["recipe_id"]).first()
    if rec_db:
        db.delete(rec_db)
        db.commit()
    db.close()


def test_create_alternative_to_shared_recipe():
    """Ensure a user can create an alternative recipe referencing a recipe shared by another user."""
    db = SessionLocal()
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    lisa = next(a for a in accounts if a["username"] == "lisa")

    for old in db.query(Recipe).filter_by(title="Risotto crémeux de Lisa").all():
        db.delete(old)
    for old in db.query(Recipe).filter_by(title="Risotto aux champignons (variante Marion)").all():
        db.delete(old)
    db.commit()

    # 1. Lisa creates a recipe and shares it with Marion
    lisa_recipe = client.post("/api/recipes", json={
        "account_id": lisa["id"],
        "title": "Risotto crémeux de Lisa",
        "instructions": "Cuire le riz avec le bouillon petit à petit.",
        "prep_time_minutes": 10,
        "cook_time_minutes": 25,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {"name": "Pâtes", "category": "féculent", "quantity": 250, "unit": "g", "importance": 3}
        ]
    }).json()
    lisa_rec_id = lisa_recipe["recipe_id"]

    client.post(f"/api/recipes/{lisa_rec_id}/share", json={"target_account_id": marion["id"]})

    # 2. Marion creates an alternative recipe referencing Lisa's shared recipe
    marion_alt = client.post("/api/recipes", json={
        "account_id": marion["id"],
        "title": "Risotto aux champignons (variante Marion)",
        "instructions": "Ajouter des champignons sautés au risotto de Lisa.",
        "prep_time_minutes": 15,
        "cook_time_minutes": 25,
        "base_servings": 4,
        "visibility": "private",
        "parent_recipe_id": lisa_rec_id,
        "ingredients": [
            {"name": "Pâtes", "category": "féculent", "quantity": 250, "unit": "g", "importance": 3}
        ]
    })
    assert marion_alt.status_code == 201
    alt_data = marion_alt.json()
    assert alt_data["is_alternative"] is True
    assert alt_data["parent_recipe_id"] == lisa_rec_id
    assert alt_data["parent_recipe_title"] == "Risotto crémeux de Lisa"

    # Cleanup
    rec_alt_db = db.query(Recipe).filter_by(id=alt_data["recipe_id"]).first()
    if rec_alt_db:
        db.delete(rec_alt_db)
    rec_orig_db = db.query(Recipe).filter_by(id=lisa_rec_id).first()
    if rec_orig_db:
        db.delete(rec_orig_db)
    db.commit()
    db.close()


def test_allow_same_title_with_different_quantities():
    """Ensure a user can create another recipe with the same title if quantities differ."""
    db = SessionLocal()
    for old in db.query(Recipe).filter_by(title="Tarte aux pommes familiale").all():
        db.delete(old)
    db.commit()

    base_payload = {
        "account_id": 1,
        "title": "Tarte aux pommes familiale",
        "instructions": "Cuire la tarte.",
        "prep_time_minutes": 20,
        "cook_time_minutes": 30,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {"name": "Pomme", "category": "fruit", "quantity": 500, "unit": "g", "importance": 3}
        ]
    }
    r1 = client.post("/api/recipes", json=base_payload)
    assert r1.status_code == 201

    # Same title, different quantity (800g instead of 500g)
    variant_payload = {
        **base_payload,
        "base_servings": 6,
        "ingredients": [
            {"name": "Pomme", "category": "fruit", "quantity": 800, "unit": "g", "importance": 3}
        ]
    }
    r2 = client.post("/api/recipes", json=variant_payload)
    assert r2.status_code == 201
    assert r2.json()["recipe_id"] != r1.json()["recipe_id"]

    # Same title, exact same ingredient & quantity -> must be rejected (400)
    dup_payload = {
        **base_payload,
        "ingredients": [
            {"name": "Pomme", "category": "fruit", "quantity": 500, "unit": "g", "importance": 3}
        ]
    }
    r3 = client.post("/api/recipes", json=dup_payload)
    assert r3.status_code == 400
    assert "exactement les mêmes ingrédients et quantités" in r3.json()["detail"]

    # Cleanup
    for old in db.query(Recipe).filter_by(title="Tarte aux pommes familiale").all():
        db.delete(old)
    db.commit()
    db.close()


def test_shared_recipe_update_notification_and_response():
    """Ensure updating a shared recipe notifies recipient, and accept/reject works."""
    db = SessionLocal()
    accounts = client.get("/api/accounts").json()
    marion = next(a for a in accounts if a["username"] == "marion")
    lisa = next(a for a in accounts if a["username"] == "lisa")

    for old in db.query(Recipe).filter(Recipe.title.like("%Curry doux%")).all():
        db.delete(old)
    db.query(RecipeUpdateNotification).filter(RecipeUpdateNotification.recipe_title.like("%Curry doux%")).delete()
    db.commit()

    # 1. Marion creates a recipe and shares it with Lisa
    r_create = client.post("/api/recipes", json={
        "account_id": marion["id"],
        "title": "Curry doux de Marion",
        "instructions": "Mijoter le curry.",
        "prep_time_minutes": 15,
        "cook_time_minutes": 25,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {"name": "Carotte", "category": "légume", "quantity": 300, "unit": "g", "importance": 3}
        ]
    }).json()
    rec_id = r_create["recipe_id"]

    client.post(f"/api/recipes/{rec_id}/share", json={"target_account_id": lisa["id"]})

    # 2. Marion updates the recipe
    update_res = client.put(f"/api/recipes/{rec_id}", json={
        "account_id": marion["id"],
        "title": "Curry doux de Marion (recette révisée)",
        "instructions": "Mijoter le curry avec du lait de coco.",
        "prep_time_minutes": 20,
        "cook_time_minutes": 30,
        "base_servings": 4,
        "visibility": "private",
        "ingredients": [
            {"name": "Carotte", "category": "légume", "quantity": 400, "unit": "g", "importance": 3}
        ]
    })
    assert update_res.status_code == 200

    # 3. Lisa checks notifications
    notif_res = client.get(f"/api/accounts/{lisa['id']}/notifications")
    assert notif_res.status_code == 200
    notifications = notif_res.json()
    curry_notifs = [n for n in notifications if n["recipe_id"] == rec_id and n["status"] == "pending"]
    assert len(curry_notifs) == 1
    notif = curry_notifs[0]
    assert "a modifié la recette" in notif["message"]

    # 4. Lisa rejects modification -> restores pre-modification version in Lisa's account
    resp = client.post(f"/api/notifications/{notif['id']}/respond", json={"action": "reject"})
    assert resp.status_code == 200
    assert "conservée dans votre carnet" in resp.json()["message"]

    # Notification should now be marked rejected in DB and no longer pending
    db.expire_all()
    notif_in_db = db.query(RecipeUpdateNotification).filter_by(id=notif["id"]).first()
    assert notif_in_db.status == "rejected"
    pending_check = client.get(f"/api/accounts/{lisa['id']}/notifications").json()
    assert not any(n["id"] == notif["id"] for n in pending_check)

    # Cleanup
    for old in db.query(Recipe).filter(Recipe.title.like("%Curry doux%")).all():
        db.delete(old)
    db.query(RecipeUpdateNotification).filter(RecipeUpdateNotification.recipe_title.like("%Curry doux%")).delete()
    db.commit()
    db.close()


def test_sync_supabase_user():
    """Ensure Supabase user sync links existing accounts and creates new ones with default profiles."""
    db = SessionLocal()

    # 1. Sync existing Marion test account
    sync_res = client.post("/api/auth/sync", json={
        "supabase_uid": "sup-uid-marion-12345",
        "email": "marion@test.fr",
        "display_name": "Marion"
    })
    assert sync_res.status_code == 200
    m_data = sync_res.json()
    assert m_data["email"] == "marion@test.fr"
    assert m_data["username"] == "marion"

    # Verify UID was stored
    acc_db = db.query(UserAccount).filter_by(id=m_data["id"]).first()
    assert acc_db.supabase_uid == "sup-uid-marion-12345"

    # 2. Sync brand new user
    new_email = "new_visitor_test@foodchoice.fr"
    db.query(UserAccount).filter_by(email=new_email).delete()
    db.commit()

    sync_new = client.post("/api/auth/sync", json={
        "supabase_uid": "sup-uid-new-user-9999",
        "email": new_email,
        "display_name": "Nouveau Visiteur"
    })
    assert sync_new.status_code == 200
    new_data = sync_new.json()
    assert new_data["display_name"] == "Nouveau Visiteur"
    assert new_data["email"] == new_email

    # Verify a default dining profile was automatically created
    prof = db.query(HouseholdProfile).filter_by(account_id=new_data["id"]).first()
    assert prof is not None
    assert prof.name == "Nouveau Visiteur"

    # Cleanup
    db.query(HouseholdProfile).filter_by(account_id=new_data["id"]).delete()
    db.query(UserAccount).filter_by(id=new_data["id"]).delete()
    db.commit()
    db.close()


