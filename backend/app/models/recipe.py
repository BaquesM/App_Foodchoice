"""SQLAlchemy database models for accounts, recipes, ingredients, and sharing."""
import json
import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class UserAccount(Base):
    """User account representing the person who logs in (e.g. Marion, Lisa, Odile)."""
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=True)
    supabase_uid = Column(String(100), unique=True, index=True, nullable=True)

    # Relationships
    household_profiles = relationship("HouseholdProfile", back_populates="account", cascade="all, delete-orphan")
    recipes = relationship("Recipe", back_populates="author", cascade="all, delete-orphan")
    received_shares = relationship("RecipeShare", back_populates="shared_with_account", cascade="all, delete-orphan")


class HouseholdProfile(Base):
    """Household/dining guest profile belonging to an account (e.g. Marion, Thomas)."""
    __tablename__ = "household_profiles"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)
    name = Column(String(100), nullable=False)

    account = relationship("UserAccount", back_populates="household_profiles")
    preferences = relationship("UserIngredientPreference", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("account_id", "name", name="unique_account_profile_name"),
    )


class Ingredient(Base):
    """Base culinary ingredient."""
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    category = Column(String(50), nullable=False)  # vegetable, fruit, meat, dairy, etc.
    needs_season_review = Column(Boolean, default=False, nullable=False)
    
    # Available months stored as JSON string (e.g. "[5, 6, 7, 8, 9]")
    _available_months = Column("available_months", String(100), default="[1,2,3,4,5,6,7,8,9,10,11,12]")

    @property
    def available_months(self) -> list[int]:
        """Return available months (1-12) as a Python list of integers."""
        try:
            return json.loads(self._available_months)
        except Exception:
            return list(range(1, 13))

    @available_months.setter
    def available_months(self, months: list[int]):
        """Persist available months as a sorted JSON array."""
        self._available_months = json.dumps(sorted(list(set(months))))


class Recipe(Base):
    """Culinary recipe with private/public visibility and sharing capabilities."""
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)
    title = Column(String(200), nullable=False, index=True)
    instructions = Column(Text, nullable=False)
    prep_time_minutes = Column(Integer, default=15)
    cook_time_minutes = Column(Integer, default=20)
    base_servings = Column(Integer, default=4)

    # Visibility: "private" (only author + explicitly shared) or "public" (open to everyone including guests)
    visibility = Column(String(20), default="private", nullable=False)

    # Option C: Unique shareable token for direct link access
    share_token = Column(String(64), unique=True, index=True, default=lambda: uuid.uuid4().hex[:12])

    # Optional reference to an original recipe if this is an alternative variation
    parent_recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)

    # Relationships
    author = relationship("UserAccount", back_populates="recipes")
    recipe_ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    shares = relationship("RecipeShare", back_populates="recipe", cascade="all, delete-orphan")
    parent_recipe = relationship("Recipe", remote_side=[id], backref="alternatives")


class RecipeShare(Base):
    """Option B: Direct sharing from one account to another account."""
    __tablename__ = "recipe_shares"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    shared_with_account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)

    recipe = relationship("Recipe", back_populates="shares")
    shared_with_account = relationship("UserAccount", back_populates="received_shares")

    __table_args__ = (
        UniqueConstraint("recipe_id", "shared_with_account_id", name="unique_recipe_account_share"),
    )


class RecipeIngredient(Base):
    """Association table linking a Recipe to an Ingredient with quantity and importance."""
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), default="g")
    
    # 1 = Optional/Garnish, 2 = Major, 3 = Essential
    importance = Column(Integer, default=2)

    recipe = relationship("Recipe", back_populates="recipe_ingredients")
    ingredient = relationship("Ingredient")


class Substitution(Base):
    """Substitution rule between ingredients."""
    __tablename__ = "substitutions"

    id = Column(Integer, primary_key=True, index=True)
    original_ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    substitute_ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    ratio = Column(Float, default=1.0)
    note = Column(String(255), default="")

    original_ingredient = relationship("Ingredient", foreign_keys=[original_ingredient_id])
    substitute_ingredient = relationship("Ingredient", foreign_keys=[substitute_ingredient_id])


class UserIngredientPreference(Base):
    """Preference rating of a household member for a given ingredient."""
    __tablename__ = "user_ingredient_preferences"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("household_profiles.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    # -2 = Dislike strongly / Veto
    # -1 = Dislike slightly
    #  0 = Neutral
    # +1 = Like
    # +2 = Love
    rating = Column(Integer, default=0)

    profile = relationship("HouseholdProfile", back_populates="preferences")
    ingredient = relationship("Ingredient")

    __table_args__ = (
        UniqueConstraint("profile_id", "ingredient_id", name="unique_profile_ingredient_pref"),
    )


class RecipeUpdateNotification(Base):
    """Notification sent when an author modifies a shared recipe."""
    __tablename__ = "recipe_update_notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)
    recipient_account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)
    recipe_title = Column(String(200), nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # "pending", "accepted", "rejected"
    message = Column(Text, nullable=False)
    previous_snapshot = Column(Text, nullable=True)

    recipe = relationship("Recipe")
    author = relationship("UserAccount", foreign_keys=[author_id])
    recipient_account = relationship("UserAccount", foreign_keys=[recipient_account_id])
