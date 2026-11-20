"""Pydantic schemas defining request and response contracts."""
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class IngredientOut(BaseModel):
    """Ingredient output schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    available_months: list[int]
    needs_season_review: bool = False


class UserAccountOut(BaseModel):
    """User account output schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str


class HouseholdProfileCreate(BaseModel):
    """Payload to create a new household dining guest profile."""
    name: str = Field(..., min_length=2, max_length=100)


class HouseholdProfileOut(BaseModel):
    """Household dining profile output schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    name: str


class ProfilePreferenceItemOut(BaseModel):
    """Saved preference for a profile."""
    ingredient_id: int
    ingredient_name: str
    category: str
    rating: int


class PreferenceIn(BaseModel):
    """User ingredient preference submission schema."""
    profile_id: int
    ingredient_id: int
    rating: int = Field(..., ge=-2, le=2, description="Rating from -2 (hate) to +2 (love)")


class PreferenceOut(BaseModel):
    """Preference confirmation response."""
    profile_id: int
    ingredient_id: int
    rating: int
    message: str


class RecipeIngredientCreate(BaseModel):
    """Ingredient entry when creating a recipe."""
    ingredient_id: Optional[int] = Field(default=None, description="Existing ingredient ID")
    name: Optional[str] = Field(default=None, description="Ingredient name (if new or identified by name)")
    category: Optional[str] = Field(default="autre", description="Family/category of ingredient (protéine, légume, etc.)")
    quantity: float = Field(gt=0, description="Quantity of ingredient")
    unit: str = Field(default="g", description="Unit (g, ml, pièce...)")
    importance: int = Field(default=2, ge=1, le=3, description="1=Optional, 2=Major, 3=Essential")
    available_months: Optional[list[int]] = Field(default=None, description="Months in season (1-12) for new ingredient")
    season_unknown: bool = Field(default=False, description="Whether user selected 'Je sais pas' to warn admin for manual review")
    substitute_name: Optional[str] = Field(default=None, description="Free-text name of substitute ingredient (new or existing)")
    substitute_ingredient_id: Optional[int] = Field(default=None, description="Optional substitute ingredient ID")
    substitute_quantity: Optional[float] = Field(default=None, gt=0, description="Quantity of substitute ingredient")
    substitute_unit: Optional[str] = Field(default="g", description="Unit of measurement for substitute ingredient")
    substitute_ratio: float = Field(default=1.0, gt=0, description="Conversion ratio for substitution")
    substitute_note: str = Field(default="", description="Optional culinary note for substitution")


class RecipeCreate(BaseModel):
    """Recipe creation request payload."""
    account_id: int
    title: str = Field(..., min_length=2, max_length=200)
    instructions: str = Field(..., min_length=5)
    prep_time_minutes: int = Field(default=15, ge=0)
    cook_time_minutes: int = Field(default=20, ge=0)
    base_servings: int = Field(default=4, ge=1)
    visibility: str = Field(default="private", pattern="^(private|public)$")
    parent_recipe_id: Optional[int] = Field(default=None, description="Optional ID of original recipe if this is an alternative variation")
    ingredients: list[RecipeIngredientCreate] = Field(..., min_length=1)


class RecipeUpdate(RecipeCreate):
    """Recipe modification request payload."""
    pass


class RecipeShareCreate(BaseModel):
    """Target account for sharing a recipe (Option B)."""
    target_account_id: int


class SearchRequest(BaseModel):
    """Search and recommendation request payload."""
    account_id: Optional[int] = Field(default=None, description="Active account ID (null for anonymous guest)")
    profile_ids: list[int] = Field(default_factory=list, description="IDs of dining household profiles")
    ingredient_ids: list[int] = Field(default_factory=list, description="IDs of possessed ingredients")
    target_servings: Optional[int] = Field(default=None, gt=0, description="Desired number of servings")
    month: Optional[int] = Field(default=None, ge=1, le=12, description="Target calendar month (1-12)")
    min_match_score: float = Field(default=50.0, ge=0.0, le=100.0, description="Minimum compatibility score threshold")
    include_public: bool = Field(default=True, description="Whether to include public recipes in search results")


class SubstitutionInfo(BaseModel):
    """Substitution details attached to an ingredient match."""
    substitute_id: int
    substitute_name: str
    ratio: float
    substituted_quantity: float
    unit: str
    note: str
    reason: str


class IngredientMatchOut(BaseModel):
    """Detailed ingredient match state."""
    ingredient_id: int
    name: str
    category: str
    quantity: float
    unit: str
    importance: int
    status: str
    in_season: bool
    substitution: Optional[SubstitutionInfo] = None
    user_opinions: list[dict] = Field(default_factory=list)


class RecipeRecommendationOut(BaseModel):
    """Recommended recipe output schema."""
    recipe_id: int
    title: str
    instructions: str
    prep_time_minutes: int
    cook_time_minutes: int
    servings: int
    visibility: str
    share_token: str
    author_name: str
    is_own: bool
    is_alternative: bool = False
    parent_recipe_id: Optional[int] = None
    parent_recipe_title: Optional[str] = None
    has_alternatives: bool = False
    match_score: float
    seasonality_score: float
    preference_score: float
    has_veto: bool
    veto_reasons: list[str]
    shared_with: list[str] = Field(default_factory=list, description="Names of accounts with whom recipe is shared")
    shared_with_ids: list[int] = Field(default_factory=list, description="IDs of accounts with whom recipe is shared")
    ingredients: list[IngredientMatchOut]


class RecipeNotificationOut(BaseModel):
    """Notification item output."""
    id: int
    recipe_id: int
    recipe_title: str
    author_id: int
    author_name: str
    recipient_account_id: int
    status: str
    message: str


class NotificationResponse(BaseModel):
    """Action response to a recipe update notification ('accept' or 'reject')."""
    action: str
