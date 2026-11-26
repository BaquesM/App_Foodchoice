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
from sqlalchemy import Table
from backend.app.db.session import Base

MONTH_COLUMNS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

NON_VEGETARIAN_CATEGORIES = {"viande", "poisson"}
NON_VEGAN_CATEGORIES = {"viande", "poisson", "produit laitier", "fromage"}
NON_VEGETARIAN_ALLERGENS = {"poissons", "crustaces", "mollusques"}
NON_VEGAN_ALLERGENS = {"lait", "oeufs", "poissons", "crustaces", "mollusques"}


def infer_diets(category: str, allergen_names=()) -> tuple[bool, bool]:
    """Infer (is_vegetarian, is_vegan) from an ingredient's category and allergen slugs."""
    cat = (category or "").strip().lower()
    allergens = set(allergen_names or ())
    is_vegetarian = (cat not in NON_VEGETARIAN_CATEGORIES) and not (allergens & NON_VEGETARIAN_ALLERGENS)
    is_vegan = (cat not in NON_VEGAN_CATEGORIES) and not (allergens & NON_VEGAN_ALLERGENS)
    return is_vegetarian, is_vegan

# Many-to-many link: an ingredient has 0..n allergens
ingredient_allergens = Table(
    "ingredient_allergens",
    Base.metadata,
    Column("ingredient_id", Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True),
    Column("allergen_id", Integer, ForeignKey("allergens.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-many link: a household profile has 0..n allergens
profile_allergens = Table(
    "profile_allergens",
    Base.metadata,
    Column("profile_id", Integer, ForeignKey("household_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("allergen_id", Integer, ForeignKey("allergens.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-many link: a recipe can declare 0..n extra allergens manually
recipe_allergens = Table(
    "recipe_allergens",
    Base.metadata,
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    Column("allergen_id", Integer, ForeignKey("allergens.id", ondelete="CASCADE"), primary_key=True),
)


class UserAccount(Base):
    """User account representing the person who logs in (e.g. Curie, Einstein, Newton)."""
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
    is_vegetarian = Column(Boolean, default=False, nullable=False)
    is_vegan = Column(Boolean, default=False, nullable=False)

    account = relationship("UserAccount", back_populates="household_profiles")
    preferences = relationship("UserIngredientPreference", back_populates="profile", cascade="all, delete-orphan")
    allergen_links = relationship("Allergen", secondary=profile_allergens)

    @property
    def allergens(self) -> list[str]:
        """Return the names of the allergens avoided by this profile."""
        return sorted(a.name for a in self.allergen_links)

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

    # 1..1 seasonality row (12 booleans), 1..1 diet row, and 0..n allergens (many-to-many)
    season = relationship(
        "IngredientSeason", back_populates="ingredient", uselist=False,
        cascade="all, delete-orphan",
    )
    diet = relationship(
        "IngredientDiet", back_populates="ingredient", uselist=False,
        cascade="all, delete-orphan",
    )
    allergen_links = relationship("Allergen", secondary=ingredient_allergens, back_populates="ingredients")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.diet is None:
            self.sync_diet()

    def sync_diet(self) -> None:
        """Recompute is_vegetarian and is_vegan from category and allergens."""
        is_veg, is_vgn = infer_diets(self.category or "", self.allergens)
        if self.diet is None:
            self.diet = IngredientDiet(is_vegetarian=is_veg, is_vegan=is_vgn)
        else:
            self.diet.is_vegetarian = is_veg
            self.diet.is_vegan = is_vgn

    @property
    def available_months(self) -> list[int]:
        """Return available months (1-12) as a sorted list of integers."""
        if self.season is None:
            return list(range(1, 13))
        return self.season.months

    @available_months.setter
    def available_months(self, months: list[int]):
        """Persist available months into the seasonality row."""
        if self.season is None:
            self.season = IngredientSeason()
        self.season.months = months

    @property
    def allergens(self) -> list[str]:
        """Return the names of the allergens contained in this ingredient."""
        return sorted(a.name for a in self.allergen_links)

    @property
    def is_vegetarian(self) -> bool:
        """Return whether this ingredient is vegetarian."""
        if self.diet is None:
            return infer_diets(self.category or "", self.allergens)[0]
        return self.diet.is_vegetarian

    @property
    def is_vegan(self) -> bool:
        """Return whether this ingredient is vegan."""
        if self.diet is None:
            return infer_diets(self.category or "", self.allergens)[1]
        return self.diet.is_vegan


class IngredientSeason(Base):
    """Seasonality of an ingredient: one boolean per month (1..1 with Ingredient)."""
    __tablename__ = "ingredient_seasons"

    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True)
    jan = Column(Boolean, default=True, nullable=False)
    feb = Column(Boolean, default=True, nullable=False)
    mar = Column(Boolean, default=True, nullable=False)
    apr = Column(Boolean, default=True, nullable=False)
    may = Column(Boolean, default=True, nullable=False)
    jun = Column(Boolean, default=True, nullable=False)
    jul = Column(Boolean, default=True, nullable=False)
    aug = Column(Boolean, default=True, nullable=False)
    sep = Column(Boolean, default=True, nullable=False)
    oct = Column(Boolean, default=True, nullable=False)
    nov = Column(Boolean, default=True, nullable=False)
    dec = Column(Boolean, default=True, nullable=False)

    ingredient = relationship("Ingredient", back_populates="season")

    @property
    def months(self) -> list[int]:
        """Months (1-12) flagged as in season."""
        return [i for i, col in enumerate(MONTH_COLUMNS, start=1) if getattr(self, col)]

    @months.setter
    def months(self, values: list[int]):
        wanted = set(values)
        for i, col in enumerate(MONTH_COLUMNS, start=1):
            setattr(self, col, i in wanted)


class IngredientDiet(Base):
    """Dietary flags for an ingredient (1..1 with Ingredient)."""
    __tablename__ = "ingredient_diets"

    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True)
    is_vegetarian = Column(Boolean, default=True, nullable=False)
    is_vegan = Column(Boolean, default=True, nullable=False)

    ingredient = relationship("Ingredient", back_populates="diet")


class Allergen(Base):
    """Reference list of allergens (EU 14 major allergens)."""
    __tablename__ = "allergens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)  # slug, e.g. "fruits_a_coque"
    label = Column(String(100), nullable=False)  # display name, e.g. "Fruits à coque"

    ingredients = relationship("Ingredient", secondary=ingredient_allergens, back_populates="allergen_links")


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
    is_freezable = Column(Boolean, default=False, nullable=False)

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
    allergen_links = relationship("Allergen", secondary=recipe_allergens)

    @property
    def allergens(self) -> list[str]:
        """Return manually declared allergen slugs on this recipe."""
        return sorted(a.name for a in self.allergen_links)


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
