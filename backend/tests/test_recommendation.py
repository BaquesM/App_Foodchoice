import pytest
from backend.app.db.session import SessionLocal
from backend.app.models.recipe import Ingredient, UserAccount, HouseholdProfile, Recipe
from backend.app.services.recommendation import search_and_rank_recipes

@pytest.fixture
def db_session():
    """Provide a clean database session for test execution."""
    db = SessionLocal()
    yield db
    db.close()

def test_missing_low_importance_ingredient_gives_high_score(db_session):
    """
    Missing only low-importance chives (importance 1) in Omelet (total weight 6)
    should yield: (3 + 2) / 6 = 83.3%.
    """
    marion = db_session.query(UserAccount).filter_by(username="marion").first()
    oeuf = db_session.query(Ingredient).filter_by(name="Oeuf").first()
    beurre = db_session.query(Ingredient).filter_by(name="Beurre").first()

    results = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[oeuf.id, beurre.id],
        account_id=marion.id,
    )

    omelette = next(r for r in results if r.title == "Omelette aux fines herbes")
    assert omelette.match_score == pytest.approx(83.3, abs=0.2)
    assert results[0].recipe_id == omelette.recipe_id

def test_servings_scaling(db_session):
    """
    Ensure quantities scale proportionally when changing servings from 2 to 4.
    """
    marion = db_session.query(UserAccount).filter_by(username="marion").first()
    oeuf = db_session.query(Ingredient).filter_by(name="Oeuf").first()
    results = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[oeuf.id],
        account_id=marion.id,
        target_servings=4
    )
    omelette = next(r for r in results if r.title == "Omelette aux fines herbes")
    oeuf_match = next(i for i in omelette.ingredients if i.name == "Oeuf")
    assert oeuf_match.quantity == 8.0

def test_user_veto_detection(db_session):
    """
    Thomas dislikes Tomato strongly (rating -2).
    When Thomas is dining, the Tomato Mozzarella salad must trigger a veto.
    """
    marion = db_session.query(UserAccount).filter_by(username="marion").first()
    thomas = db_session.query(HouseholdProfile).filter_by(account_id=marion.id, name="Thomas").first()
    tomate = db_session.query(Ingredient).filter_by(name="Tomate").first()
    mozzarella = db_session.query(Ingredient).filter_by(name="Mozzarella").first()

    results = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[tomate.id, mozzarella.id],
        account_id=marion.id,
        profile_ids=[thomas.id],
    )

    salade = next(r for r in results if r.title == "Salade Tomate Mozzarella")
    assert salade.has_veto is True
    assert any("Thomas déteste Tomate" in reason for reason in salade.veto_reasons)

def test_anonymous_guest_only_sees_public_recipes(db_session):
    """
    Anonymous guest (account_id=None) only sees recipes with visibility='public'.
    Private recipes (like Marion's Omelette) are excluded.
    """
    results = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[],
        account_id=None,
        min_match_score=0.0,
    )

    titles = [r.title for r in results]
    assert "Pâtes Carbonara" in titles  # public
    assert "Omelette aux fines herbes" not in titles  # private to Marion

def test_option_b_sharing_between_accounts(db_session):
    """
    Lisa's salad is private, but explicitly shared with Marion (Option B).
    Marion must see it, while Odile cannot.
    """
    marion = db_session.query(UserAccount).filter_by(username="marion").first()
    odile = db_session.query(UserAccount).filter_by(username="odile").first()

    marion_results = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[],
        account_id=marion.id,
        min_match_score=0.0,
    )
    marion_titles = [r.title for r in marion_results]
    assert "Salade Tomate Mozzarella" in marion_titles

    odile_results = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[],
        account_id=odile.id,
        min_match_score=0.0,
    )
    odile_titles = [r.title for r in odile_results]
    assert "Salade Tomate Mozzarella" not in odile_titles

def test_include_public_toggle(db_session):
    """
    Ensure include_public=False excludes public recipes from others,
    while keeping the user's own and directly shared recipes.
    """
    odile = db_session.query(UserAccount).filter_by(username="odile").first()
    # Add a public recipe owned by Odile
    odile_recipe = Recipe(
        account_id=odile.id,
        title="Ratatouille d'Odile",
        instructions="Mijoter les légumes.",
        visibility="public",
    )
    db_session.add(odile_recipe)
    db_session.commit()

    marion = db_session.query(UserAccount).filter_by(username="marion").first()

    # Search with include_public=True
    with_public = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[],
        account_id=marion.id,
        min_match_score=0.0,
        include_public=True,
    )
    assert any(r.title == "Ratatouille d'Odile" for r in with_public)

    # Search with include_public=False
    without_public = search_and_rank_recipes(
        db=db_session,
        available_ingredient_ids=[],
        account_id=marion.id,
        min_match_score=0.0,
        include_public=False,
    )
    assert not any(r.title == "Ratatouille d'Odile" for r in without_public)
