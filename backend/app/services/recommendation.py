"""Recommendation, compatibility scoring, and substitution engine."""
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from backend.app.models.recipe import (
    Recipe,
    RecipeShare,
    Ingredient,
    RecipeIngredient,
    Substitution,
    HouseholdProfile,
    UserIngredientPreference,
)

@dataclass
class IngredientMatch:
    """State of an ingredient for a given recipe match."""
    ingredient_id: int
    name: str
    category: str
    quantity: float
    unit: str
    importance: int
    status: str  # "available", "substituted", "missing"
    in_season: bool
    substitution: Optional[dict] = None
    user_opinions: list[dict] = field(default_factory=list)

@dataclass
class RecipeRecommendation:
    """Complete recommendation result for a recipe."""
    recipe_id: int
    title: str
    instructions: str
    prep_time_minutes: int
    cook_time_minutes: int
    servings: int
    visibility: str  # "private" or "public"
    share_token: str
    author_name: str
    is_own: bool  # True if authored by active account
    match_score: float  # 0.0 to 100.0 %
    seasonality_score: float  # % of ingredients in season
    preference_score: float  # Average rating from dining users (-2 to +2)
    has_veto: bool  # True if any dining user gave -2 with no valid substitution
    is_alternative: bool = False
    parent_recipe_id: Optional[int] = None
    parent_recipe_title: Optional[str] = None
    has_alternatives: bool = False
    veto_reasons: list[str] = field(default_factory=list)
    shared_with: list[str] = field(default_factory=list)
    shared_with_ids: list[int] = field(default_factory=list)
    ingredients: list[IngredientMatch] = field(default_factory=list)


def search_and_rank_recipes(
    db: Session,
    available_ingredient_ids: list[int],
    target_servings: Optional[int] = None,
    account_id: Optional[int] = None,
    profile_ids: Optional[list[int]] = None,
    current_month: Optional[int] = None,
    min_match_score: float = 50.0,
    include_public: bool = True,
    target_recipe_ids: Optional[list[int]] = None,
) -> list[RecipeRecommendation]:
    """
    Search and rank recipes based on:
    1. Account accessibility:
       - Guest (account_id=None): only sees public recipes (or specific target_recipe_ids via share token).
       - Logged-in account: sees own recipes + specifically shared recipes (+ public recipes if include_public=True).
    2. Compatibility score with possessed ingredients (weighted by importance).
    3. Available substitutions for missing or disliked ingredients.
    4. Multi-user consensus of selected household profiles (dislike penalties and veto detection).
    5. Ingredient seasonality.
    6. Minimum match score threshold.
    """
    if current_month is None:
        current_month = datetime.now().month

    profile_ids = profile_ids or []
    available_set = set(available_ingredient_ids)

    # 1. Determine accessible recipes
    if target_recipe_ids is not None:
        # Explicit target recipe list (e.g. accessed via unique share token)
        candidate_recipes = db.query(Recipe).filter(Recipe.id.in_(target_recipe_ids)).all()
    elif account_id is None:
        # Anonymous guest: only public recipes are accessible
        candidate_recipes = db.query(Recipe).filter(Recipe.visibility == "public").all()
        # Guests have no private household profiles to evaluate
        profile_ids = []
    else:
        # Logged-in user:
        # - Own recipes (private or public)
        # - Recipes explicitly shared with this account (Option B)
        # - Public recipes from other users (if include_public is True)
        shared_recipe_ids = [
            s.recipe_id
            for s in db.query(RecipeShare).filter_by(shared_with_account_id=account_id).all()
        ]

        conditions = (Recipe.account_id == account_id) | (Recipe.id.in_(shared_recipe_ids))
        if include_public:
            conditions = conditions | (Recipe.visibility == "public")

        candidate_recipes = db.query(Recipe).filter(conditions).all()

    # 2. Fetch household profile opinions (only from profiles belonging to this search)
    profile_prefs_map = {}  # {profile_id: {ingredient_id: rating}}
    profile_names = {}
    if profile_ids:
        profiles = db.query(HouseholdProfile).filter(HouseholdProfile.id.in_(profile_ids)).all()
        for p in profiles:
            profile_names[p.id] = p.name
            profile_prefs_map[p.id] = {}

        prefs = (
            db.query(UserIngredientPreference)
            .filter(UserIngredientPreference.profile_id.in_(profile_ids))
            .all()
        )
        for pref in prefs:
            profile_prefs_map[pref.profile_id][pref.ingredient_id] = pref.rating

    # 3. Fetch all registered substitutions
    all_substitutions = db.query(Substitution).all()
    sub_map: dict[int, list[Substitution]] = {}
    for sub in all_substitutions:
        sub_map.setdefault(sub.original_ingredient_id, []).append(sub)

    recommendations: list[RecipeRecommendation] = []

    for recipe in candidate_recipes:
        base_servings = recipe.base_servings or 1
        servings = target_servings if target_servings and target_servings > 0 else base_servings
        scaling_ratio = servings / base_servings

        total_weight = 0
        earned_weight = 0.0
        ingredients_in_season_count = 0
        all_recipe_ratings = []
        has_veto = False
        veto_reasons = []
        ingredient_matches: list[IngredientMatch] = []

        for ri in recipe.recipe_ingredients:
            ing = ri.ingredient
            if not ing:
                continue
            weight = ri.importance  # 1, 2, or 3
            total_weight += weight
            scaled_qty = round(ri.quantity * scaling_ratio, 2)

            # Check seasonality
            in_season = current_month in ing.available_months
            if in_season:
                ingredients_in_season_count += 1

            # Check household opinions
            opinions = []
            disliked_by_profiles = []
            for pid in profile_ids:
                rating = profile_prefs_map.get(pid, {}).get(ing.id, 0)
                opinions.append({
                    "profile_id": pid,
                    "profile_name": profile_names.get(pid, f"Profil {pid}"),
                    "rating": rating,
                })
                all_recipe_ratings.append(rating)
                if rating <= -1:
                    disliked_by_profiles.append((pid, rating))

            # Availability and substitution resolution
            status = "missing"
            chosen_sub = None

            # Case A: Ingredient is in pantry
            if ing.id in available_set:
                # If a dining profile hates it (-2), check if an accepted substitute is available
                hate_profile = next((p for p, r in disliked_by_profiles if r == -2), None)
                if hate_profile and ing.id in sub_map:
                    for candidate_sub in sub_map[ing.id]:
                        if candidate_sub.substitute_ingredient_id in available_set:
                            sub_rating = profile_prefs_map.get(hate_profile, {}).get(candidate_sub.substitute_ingredient_id, 0)
                            if sub_rating >= 0:
                                chosen_sub = {
                                    "substitute_id": candidate_sub.substitute_ingredient_id,
                                    "substitute_name": candidate_sub.substitute_ingredient.name,
                                    "ratio": candidate_sub.ratio,
                                    "substituted_quantity": round(scaled_qty * candidate_sub.ratio, 2),
                                    "unit": ri.unit,
                                    "note": candidate_sub.note,
                                    "reason": f"Suggéré car {profile_names.get(hate_profile)} n'aime pas {ing.name}",
                                }
                                status = "substituted"
                                earned_weight += weight * 0.95
                                break

                if status != "substituted":
                    status = "available"
                    earned_weight += weight

            # Case B: Ingredient is missing; check for pantry substitute
            elif ing.id in sub_map:
                for candidate_sub in sub_map[ing.id]:
                    if candidate_sub.substitute_ingredient_id in available_set:
                        chosen_sub = {
                            "substitute_id": candidate_sub.substitute_ingredient_id,
                            "substitute_name": candidate_sub.substitute_ingredient.name,
                            "ratio": candidate_sub.ratio,
                            "substituted_quantity": round(scaled_qty * candidate_sub.ratio, 2),
                            "unit": ri.unit,
                            "note": candidate_sub.note,
                            "reason": f"Remplace {ing.name} manquant",
                        }
                        status = "substituted"
                        earned_weight += weight * 0.9
                        break

            # Veto check: if someone gave -2 and no substitute was found
            for pid, rating in disliked_by_profiles:
                if rating == -2 and status != "substituted":
                    has_veto = True
                    veto_reasons.append(f"{profile_names.get(pid)} déteste {ing.name}")

            ingredient_matches.append(
                IngredientMatch(
                    ingredient_id=ing.id,
                    name=ing.name,
                    category=ing.category,
                    quantity=scaled_qty,
                    unit=ri.unit,
                    importance=weight,
                    status=status,
                    in_season=in_season,
                    substitution=chosen_sub,
                    user_opinions=opinions,
                )
            )

        match_score = round((earned_weight / total_weight) * 100, 1) if total_weight > 0 else 0.0
        season_score = (
            round((ingredients_in_season_count / len(recipe.recipe_ingredients)) * 100, 1)
            if recipe.recipe_ingredients
            else 100.0
        )
        pref_score = (
            round(sum(all_recipe_ratings) / len(all_recipe_ratings), 2)
            if all_recipe_ratings
            else 0.0
        )

        shared_with_names = [
            s.shared_with_account.display_name
            for s in recipe.shares
            if s.shared_with_account
        ]
        shared_with_ids = [
            s.shared_with_account_id
            for s in recipe.shares
            if s.shared_with_account_id
        ]

        is_alt = recipe.parent_recipe_id is not None
        parent_title = recipe.parent_recipe.title if recipe.parent_recipe else None
        has_alts = bool(recipe.alternatives) if hasattr(recipe, "alternatives") and recipe.alternatives else False

        recommendations.append(
            RecipeRecommendation(
                recipe_id=recipe.id,
                title=recipe.title,
                instructions=recipe.instructions,
                prep_time_minutes=recipe.prep_time_minutes,
                cook_time_minutes=recipe.cook_time_minutes,
                servings=servings,
                visibility=recipe.visibility,
                share_token=recipe.share_token,
                author_name=recipe.author.display_name if recipe.author else "Inconnu",
                is_own=recipe.account_id == account_id if account_id else False,
                is_alternative=is_alt,
                parent_recipe_id=recipe.parent_recipe_id,
                parent_recipe_title=parent_title,
                has_alternatives=has_alts,
                match_score=match_score,
                seasonality_score=season_score,
                preference_score=pref_score,
                has_veto=has_veto,
                veto_reasons=veto_reasons,
                shared_with=shared_with_names,
                shared_with_ids=shared_with_ids,
                ingredients=ingredient_matches,
            )
        )

    # Filter by minimum compatibility threshold
    if available_ingredient_ids:
        # If user selected specific ingredients, keep all recipes that contain at least one of them
        recommendations = [r for r in recommendations if r.match_score > 0.0]
    elif min_match_score > 0:
        recommendations = [r for r in recommendations if r.match_score >= min_match_score]

    # Sort order: veto-free first, then descending match_score, then descending preference_score
    recommendations.sort(
        key=lambda r: (not r.has_veto, r.match_score, r.preference_score),
        reverse=True,
    )

    return recommendations
