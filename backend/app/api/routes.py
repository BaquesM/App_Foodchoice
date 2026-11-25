"""REST API route handlers for accounts, recipes, ingredients, and sharing."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from backend.app.db.session import get_db
from backend.app.models.recipe import (
    UserAccount,
    HouseholdProfile,
    Ingredient,
    Allergen,
    Recipe,
    RecipeIngredient,
    RecipeShare,
    UserIngredientPreference,
    RecipeUpdateNotification,
)
from backend.app.schemas.recipe import (
    AllergenOut,
    IngredientOut,
    UserAccountOut,
    HouseholdProfileCreate,
    HouseholdProfileOut,
    ProfilePreferenceItemOut,
    PreferenceIn,
    PreferenceOut,
    RecipeCreate,
    RecipeUpdate,
    RecipeShareCreate,
    SearchRequest,
    RecipeRecommendationOut,
    RecipeNotificationOut,
    NotificationResponse,
    RecipeIngredientCreate,
    AuthSyncRequest,
)
from backend.app.services.recommendation import search_and_rank_recipes

router = APIRouter(prefix="/api", tags=["Recipes & Accounts"])


@router.post("/auth/sync", response_model=UserAccountOut)
def sync_supabase_user(payload: AuthSyncRequest, db: Session = Depends(get_db)):
    """
    Synchronize an authenticated Supabase user with the application database.
    Links existing accounts by email if matching, or creates a new account.
    """
    clean_email = payload.email.strip().lower()
    clean_uid = payload.supabase_uid.strip()

    # 1. Match by supabase_uid or email
    account = db.query(UserAccount).filter(
        (UserAccount.supabase_uid == clean_uid) | (func.lower(UserAccount.email) == clean_email)
    ).first()

    if account:
        if not account.supabase_uid:
            account.supabase_uid = clean_uid
        if not account.email:
            account.email = clean_email
        if payload.display_name and (not account.display_name or account.display_name == account.username):
            account.display_name = payload.display_name.strip()
        db.commit()
        db.refresh(account)
        return account

    # 2. Create new account
    base_username = clean_email.split("@")[0].replace(".", "_")
    candidate_username = base_username
    counter = 1
    while db.query(UserAccount).filter_by(username=candidate_username).first():
        candidate_username = f"{base_username}_{counter}"
        counter += 1

    display_name = (
        payload.display_name.strip()
        if (payload.display_name and payload.display_name.strip())
        else candidate_username.replace("_", " ").title()
    )

    new_account = UserAccount(
        username=candidate_username,
        display_name=display_name,
        email=clean_email,
        supabase_uid=clean_uid,
    )
    db.add(new_account)
    db.flush()

    # Automatically create their own household dining profile
    default_profile = HouseholdProfile(account_id=new_account.id, name=new_account.display_name)
    db.add(default_profile)

    db.commit()
    db.refresh(new_account)
    return new_account


@router.get("/accounts", response_model=list[UserAccountOut])
def list_accounts(db: Session = Depends(get_db)):
    """Retrieve all user accounts (e.g. Marion, Lisa, Odile)."""
    return db.query(UserAccount).order_by(UserAccount.display_name).all()


@router.get("/accounts/{account_id}/profiles", response_model=list[HouseholdProfileOut])
def list_household_profiles(account_id: int, db: Session = Depends(get_db)):
    """Retrieve all household dining guest profiles for a specific account."""
    account = db.query(UserAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return db.query(HouseholdProfile).filter_by(account_id=account_id).order_by(HouseholdProfile.name).all()


@router.post("/accounts/{account_id}/profiles", response_model=HouseholdProfileOut, status_code=status.HTTP_201_CREATED)
def create_household_profile(account_id: int, payload: HouseholdProfileCreate, db: Session = Depends(get_db)):
    """Create a new dining guest / household profile for an account."""
    account = db.query(UserAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Profile name cannot be blank")

    existing = (
        db.query(HouseholdProfile)
        .filter_by(account_id=account_id, name=clean_name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Un profil nommé '{clean_name}' existe déjà pour ce foyer")

    new_profile = HouseholdProfile(account_id=account_id, name=clean_name)
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return new_profile


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_200_OK)
def delete_household_profile(profile_id: int, db: Session = Depends(get_db)):
    """Delete a household dining guest profile and cascade their preferences."""
    profile = db.query(HouseholdProfile).filter_by(id=profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profil de convive introuvable.")

    profile_name = profile.name
    db.delete(profile)
    db.commit()
    return {"message": f"Convive '{profile_name}' supprimé avec succès."}


@router.get("/profiles/{profile_id}/preferences", response_model=list[ProfilePreferenceItemOut])
def get_profile_preferences(profile_id: int, db: Session = Depends(get_db)):
    """Retrieve all ingredient preferences (-2 to +2) recorded for a profile."""
    profile = db.query(HouseholdProfile).filter_by(id=profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Household profile not found")

    prefs = (
        db.query(UserIngredientPreference)
        .join(Ingredient)
        .filter(UserIngredientPreference.profile_id == profile_id)
        .all()
    )

    return [
        ProfilePreferenceItemOut(
            ingredient_id=p.ingredient_id,
            ingredient_name=p.ingredient.name,
            category=p.ingredient.category,
            rating=p.rating,
        )
        for p in prefs
    ]


@router.get("/recipes/public", response_model=list[RecipeRecommendationOut])
def list_public_recipes(db: Session = Depends(get_db)):
    """Retrieve all public recipes in the community catalog (accessible to guests and all users)."""
    public_recipes = db.query(Recipe).filter_by(visibility="public").all()
    if not public_recipes:
        return []

    return search_and_rank_recipes(
        db=db,
        available_ingredient_ids=[],
        account_id=None,
        target_recipe_ids=[r.id for r in public_recipes],
        min_match_score=0.0,
    )


@router.get("/accounts/{account_id}/recipes", response_model=list[RecipeRecommendationOut])
def list_account_recipes(account_id: int, db: Session = Depends(get_db)):
    """Retrieve all personal and directly shared recipes associated with an account."""
    account = db.query(UserAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    shared_ids = [
        s.recipe_id
        for s in db.query(RecipeShare).filter_by(shared_with_account_id=account_id).all()
    ]
    recipes = (
        db.query(Recipe)
        .filter((Recipe.account_id == account_id) | (Recipe.id.in_(shared_ids)))
        .all()
    )

    if not recipes:
        return []

    return search_and_rank_recipes(
        db=db,
        available_ingredient_ids=[],
        account_id=account_id,
        target_recipe_ids=[r.id for r in recipes],
        min_match_score=0.0,
    )


@router.get("/ingredients", response_model=list[IngredientOut])
def list_ingredients(db: Session = Depends(get_db)):
    """Retrieve all ingredients sorted by category and name."""
    return db.query(Ingredient).order_by(Ingredient.category, Ingredient.name).all()


@router.get("/allergens", response_model=list[AllergenOut])
def list_allergens(db: Session = Depends(get_db)):
    """Retrieve all reference allergens sorted alphabetically by label."""
    return db.query(Allergen).order_by(Allergen.label).all()


@router.post("/recipes/search", response_model=list[RecipeRecommendationOut])
def search_recipes(payload: SearchRequest, db: Session = Depends(get_db)):
    """
    Search and rank recipes based on:
    - active account (None for anonymous guest)
    - dining household profiles (consensus & vetoes)
    - possessed ingredients
    - target servings
    - calendar month seasonality
    - minimum match score threshold
    """
    recommendations = search_and_rank_recipes(
        db=db,
        available_ingredient_ids=payload.ingredient_ids,
        target_servings=payload.target_servings,
        account_id=payload.account_id,
        profile_ids=payload.profile_ids,
        current_month=payload.month,
        min_match_score=payload.min_match_score,
        include_public=payload.include_public,
    )
    return recommendations


def _is_exact_ingredient_duplicate(db: Session, existing_recipe: Recipe, payload_ingredients: list) -> bool:
    """Check if a recipe has the exact same set of ingredients, quantities, and units."""
    existing_items = set()
    for ri in existing_recipe.recipe_ingredients:
        name = ri.ingredient.name.strip().lower() if ri.ingredient else ""
        existing_items.add((name, round(float(ri.quantity), 2), ri.unit.strip().lower()))

    payload_items = set()
    for item in payload_ingredients:
        name = ""
        if item.ingredient_id:
            ing = db.query(Ingredient).filter_by(id=item.ingredient_id).first()
            if ing:
                name = ing.name.strip().lower()
        if not name and item.name:
            name = item.name.strip().lower()
        payload_items.add((name, round(float(item.quantity), 2), (item.unit or "").strip().lower()))

    return existing_items == payload_items


def _save_recipe_ingredients(db: Session, recipe: Recipe, ingredients_payload: list, account: UserAccount):
    """Resolve and attach ingredients to a recipe."""
    for item in ingredients_payload:
        ingredient = None
        if item.ingredient_id:
            ingredient = db.query(Ingredient).filter_by(id=item.ingredient_id).first()

        if not ingredient and item.name:
            clean_name = item.name.strip()
            if clean_name:
                ingredient = db.query(Ingredient).filter(Ingredient.name.ilike(clean_name)).first()
                if not ingredient:
                    cat = item.category.strip().lower() if item.category else "autre"
                    months = (
                        item.available_months
                        if (item.available_months and len(item.available_months) > 0)
                        else list(range(1, 13))
                    )
                    is_unknown = bool(item.season_unknown)
                    ingredient = Ingredient(
                        name=clean_name.capitalize(),
                        category=cat,
                        available_months=months,
                        needs_season_review=is_unknown,
                    )
                    db.add(ingredient)
                    db.flush()

                    if is_unknown and account:
                        logger.warning(
                            f"[ADMIN AVERTISSEMENT] Nouvel ingrédient '{ingredient.name}' (catégorie: {ingredient.category}) "
                            f"créé par le compte #{account.id} ({account.display_name}) avec 'Je sais pas' pour la saisonnalité. "
                            f"Action requise : recherche manuelle des mois de récolte/saison."
                        )
                elif item.category and ingredient.category == "autre":
                    ingredient.category = item.category.strip().lower()

        if not ingredient:
            raise HTTPException(status_code=400, detail="Chaque ingrédient doit avoir un identifiant ou un nom valide.")

        if item.category and ingredient.category == "autre":
            ingredient.category = item.category.strip().lower()

        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=item.quantity,
                unit=item.unit,
                importance=item.importance,
            )
        )


@router.post("/recipes", response_model=RecipeRecommendationOut, status_code=status.HTTP_201_CREATED)
def create_recipe(payload: RecipeCreate, db: Session = Depends(get_db)):
    """Create a new recipe with its ingredients."""
    account = db.query(UserAccount).filter_by(id=payload.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    clean_title = payload.title.strip()
    same_title_recipes = (
        db.query(Recipe)
        .filter(
            Recipe.account_id == payload.account_id,
            func.lower(Recipe.title) == clean_title.lower(),
        )
        .all()
    )
    for existing in same_title_recipes:
        if _is_exact_ingredient_duplicate(db, existing, payload.ingredients):
            raise HTTPException(
                status_code=400,
                detail=f"Une recette identique avec le même titre « {clean_title} » et exactement les mêmes ingrédients et quantités existe déjà dans votre compte.",
            )

    if payload.parent_recipe_id:
        parent_rec = db.query(Recipe).filter_by(id=payload.parent_recipe_id).first()
        if not parent_rec:
            raise HTTPException(status_code=400, detail="Recette originale de référence introuvable.")

    new_recipe = Recipe(
        account_id=payload.account_id,
        title=clean_title,
        instructions=payload.instructions,
        prep_time_minutes=payload.prep_time_minutes,
        cook_time_minutes=payload.cook_time_minutes,
        base_servings=payload.base_servings,
        visibility=payload.visibility,
        parent_recipe_id=payload.parent_recipe_id,
    )
    db.add(new_recipe)
    db.flush()

    _save_recipe_ingredients(db, new_recipe, payload.ingredients, account)

    db.commit()
    db.refresh(new_recipe)

    # Return as recommendation
    single_res = search_and_rank_recipes(
        db=db,
        available_ingredient_ids=[],
        target_recipe_ids=[new_recipe.id],
        min_match_score=0.0,
    )
    matching = next((r for r in single_res if r.recipe_id == new_recipe.id), None)
    if not matching:
        raise HTTPException(status_code=500, detail="Failed to format created recipe")
    return matching


@router.put("/recipes/{recipe_id}", response_model=RecipeRecommendationOut)
def update_recipe(recipe_id: int, payload: RecipeUpdate, db: Session = Depends(get_db)):
    """Update an existing recipe owned by the active account."""
    recipe = db.query(Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recette introuvable.")

    if recipe.account_id != payload.account_id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que les recettes dont vous êtes l'auteur.")

    clean_title = payload.title.strip()
    same_title_recipes = (
        db.query(Recipe)
        .filter(
            Recipe.account_id == payload.account_id,
            Recipe.id != recipe_id,
            func.lower(Recipe.title) == clean_title.lower(),
        )
        .all()
    )
    for existing in same_title_recipes:
        if _is_exact_ingredient_duplicate(db, existing, payload.ingredients):
            raise HTTPException(
                status_code=400,
                detail=f"Une autre de vos recettes porte déjà le titre « {clean_title} » avec exactement les mêmes quantités d'ingrédients.",
            )

    if payload.parent_recipe_id:
        if payload.parent_recipe_id == recipe_id:
            raise HTTPException(status_code=400, detail="Une recette ne peut pas être sa propre alternative.")
        parent_rec = db.query(Recipe).filter_by(id=payload.parent_recipe_id).first()
        if not parent_rec:
            raise HTTPException(status_code=400, detail="Recette originale de référence introuvable.")

    account = db.query(UserAccount).filter_by(id=payload.account_id).first()

    # If the recipe is currently shared with other accounts, notify them of the modification
    if recipe.shares:
        snapshot = {
            "title": recipe.title,
            "instructions": recipe.instructions,
            "prep_time_minutes": recipe.prep_time_minutes,
            "cook_time_minutes": recipe.cook_time_minutes,
            "base_servings": recipe.base_servings,
            "ingredients": [
                {
                    "name": ri.ingredient.name,
                    "category": ri.ingredient.category,
                    "quantity": ri.quantity,
                    "unit": ri.unit,
                    "importance": ri.importance,
                }
                for ri in recipe.recipe_ingredients
                if ri.ingredient
            ],
        }
        snapshot_json = json.dumps(snapshot)
        for share in recipe.shares:
            # Create a notification for each recipient account
            notif = RecipeUpdateNotification(
                recipe_id=recipe.id,
                author_id=recipe.account_id,
                recipient_account_id=share.shared_with_account_id,
                recipe_title=clean_title,
                status="pending",
                message=f"{account.display_name} a modifié la recette « {clean_title} ». Acceptez-vous cette modification ?",
                previous_snapshot=snapshot_json,
            )
            db.add(notif)

    recipe.title = clean_title
    recipe.instructions = payload.instructions
    recipe.prep_time_minutes = payload.prep_time_minutes
    recipe.cook_time_minutes = payload.cook_time_minutes
    recipe.base_servings = payload.base_servings
    recipe.visibility = payload.visibility
    recipe.parent_recipe_id = payload.parent_recipe_id

    # Remove existing recipe ingredients for this recipe
    db.query(RecipeIngredient).filter_by(recipe_id=recipe.id).delete()

    _save_recipe_ingredients(db, recipe, payload.ingredients, account)

    db.commit()
    db.refresh(recipe)

    updated_recs = search_and_rank_recipes(
        db=db,
        available_ingredient_ids=[],
        account_id=recipe.account_id,
        target_recipe_ids=[recipe.id],
        min_match_score=0.0,
    )
    matching = next((r for r in updated_recs if r.recipe_id == recipe.id), None)
    if not matching:
        raise HTTPException(status_code=500, detail="Failed to format updated recipe")
    return matching


@router.get("/accounts/{account_id}/notifications", response_model=list[RecipeNotificationOut])
def get_account_notifications(account_id: int, db: Session = Depends(get_db)):
    """Retrieve pending recipe update notifications for an account."""
    notifs = (
        db.query(RecipeUpdateNotification)
        .filter_by(recipient_account_id=account_id, status="pending")
        .order_by(RecipeUpdateNotification.id.desc())
        .all()
    )
    return [
        RecipeNotificationOut(
            id=n.id,
            recipe_id=n.recipe_id,
            recipe_title=n.recipe_title,
            author_id=n.author_id,
            author_name=n.author.display_name if n.author else "Auteur",
            recipient_account_id=n.recipient_account_id,
            status=n.status,
            message=n.message,
        )
        for n in notifs
    ]


@router.post("/notifications/{notification_id}/respond")
def respond_to_notification(notification_id: int, payload: NotificationResponse, db: Session = Depends(get_db)):
    """Accept or reject an update to a shared recipe."""
    notif = db.query(RecipeUpdateNotification).filter_by(id=notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable.")

    if payload.action == "accept":
        notif.status = "accepted"
        db.commit()
        return {"status": "accepted", "message": f"Vous avez accepté la modification de la recette « {notif.recipe_title} »."}
    elif payload.action == "reject":
        notif.status = "rejected"
        # Detach shared link so recipient is no longer linked to author's updated recipe
        db.query(RecipeShare).filter_by(recipe_id=notif.recipe_id, shared_with_account_id=notif.recipient_account_id).delete()

        # Restore previous version in recipient's personal account so they keep their previous recipe version
        if notif.previous_snapshot:
            try:
                snap = json.loads(notif.previous_snapshot)
                clean_t = f"{snap.get('title', notif.recipe_title)} (version conservée)"
                kept_recipe = Recipe(
                    account_id=notif.recipient_account_id,
                    title=clean_t,
                    instructions=snap.get("instructions", ""),
                    prep_time_minutes=snap.get("prep_time_minutes", 15),
                    cook_time_minutes=snap.get("cook_time_minutes", 20),
                    base_servings=snap.get("base_servings", 4),
                    visibility="private",
                )
                db.add(kept_recipe)
                db.flush()
                recipient_acc = db.query(UserAccount).filter_by(id=notif.recipient_account_id).first()
                ing_objs = [RecipeIngredientCreate(**item) for item in snap.get("ingredients", [])]
                _save_recipe_ingredients(db, kept_recipe, ing_objs, recipient_acc)
            except Exception as e:
                logger.error(f"Failed to restore previous recipe snapshot: {e}")

        db.commit()
        return {
            "status": "rejected",
            "message": f"Modification refusée : votre version précédente de « {notif.recipe_title} » a été conservée dans votre carnet.",
        }
    else:
        raise HTTPException(status_code=400, detail="Action non reconnue (doit être 'accept' ou 'reject').")


@router.post("/recipes/{recipe_id}/visibility")
def update_recipe_visibility(recipe_id: int, visibility: str, db: Session = Depends(get_db)):
    """Option A: Toggle recipe visibility between 'private' and 'public'."""
    if visibility not in ("private", "public"):
        raise HTTPException(status_code=400, detail="Visibility must be 'private' or 'public'")

    recipe = db.query(Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe.visibility = visibility
    db.commit()
    return {"recipe_id": recipe.id, "visibility": recipe.visibility}


@router.post("/recipes/{recipe_id}/share")
def share_recipe_with_account(recipe_id: int, payload: RecipeShareCreate, db: Session = Depends(get_db)):
    """Option B: Share a recipe specifically with another user account."""
    recipe = db.query(Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    target = db.query(UserAccount).filter_by(id=payload.target_account_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target account not found")

    existing = (
        db.query(RecipeShare)
        .filter_by(recipe_id=recipe_id, shared_with_account_id=payload.target_account_id)
        .first()
    )
    if not existing:
        share = RecipeShare(recipe_id=recipe_id, shared_with_account_id=payload.target_account_id)
        db.add(share)
        db.commit()

    return {"message": f"Recipe '{recipe.title}' successfully shared with {target.display_name}."}


@router.get("/recipes/shared/{share_token}", response_model=RecipeRecommendationOut)
def get_recipe_by_share_token(share_token: str, db: Session = Depends(get_db)):
    """Option C: Direct access to a recipe via unique share token (publicly accessible to anyone)."""
    recipe = db.query(Recipe).filter_by(share_token=share_token).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found or invalid share token")

    res = search_and_rank_recipes(
        db=db,
        available_ingredient_ids=[],
        target_recipe_ids=[recipe.id],
        min_match_score=0.0,
    )
    target = next((r for r in res if r.recipe_id == recipe.id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Failed to load recipe details")
    return target


@router.post("/preferences", response_model=PreferenceOut, status_code=status.HTTP_200_OK)
def set_user_preference(payload: PreferenceIn, db: Session = Depends(get_db)):
    """Record or update a household profile's rating (-2 to +2) for an ingredient."""
    profile = db.query(HouseholdProfile).filter_by(id=payload.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Household profile not found")

    ingredient = db.query(Ingredient).filter_by(id=payload.ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    pref = (
        db.query(UserIngredientPreference)
        .filter_by(profile_id=payload.profile_id, ingredient_id=payload.ingredient_id)
        .first()
    )

    if pref:
        pref.rating = payload.rating
    else:
        pref = UserIngredientPreference(
            profile_id=payload.profile_id,
            ingredient_id=payload.ingredient_id,
            rating=payload.rating,
        )
        db.add(pref)

    db.commit()

    rating_labels = {
        2: "Adoré (+2)",
        1: "Aimé (+1)",
        0: "Neutre (0)",
        -1: "Pas aimé (-1)",
        -2: "Détesté / Veto (-2)",
    }
    label = rating_labels.get(payload.rating, f"{payload.rating}")

    return PreferenceOut(
        profile_id=payload.profile_id,
        ingredient_id=payload.ingredient_id,
        rating=payload.rating,
        message=f"Préférence pour '{ingredient.name}' par '{profile.name}' mise à jour : {label}.",
    )


@router.get("/admin/pending-season-ingredients", response_model=list[IngredientOut])
def get_pending_season_ingredients(db: Session = Depends(get_db)):
    """Retrieve all ingredients flagged as needing administrator season review."""
    return (
        db.query(Ingredient)
        .filter(Ingredient.needs_season_review == True)
        .order_by(Ingredient.name)
        .all()
    )
