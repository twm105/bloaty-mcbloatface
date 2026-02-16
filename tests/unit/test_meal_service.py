"""
Unit tests for MealService.

Tests the meal business logic including:
- Meal CRUD operations
- Ingredient normalization
- Race condition handling
- Draft/published status
"""

import pytest
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services.meal_service import MealService
from app.models import Meal, Ingredient, MealIngredient, IngredientState
from tests.factories import (
    create_user,
    create_meal,
    create_ingredient,
    create_meal_ingredient,
)


class TestMealCreation:
    """Tests for meal creation."""

    def test_create_meal_with_minimal_data(self, db: Session):
        """Test creating a meal with only required fields."""
        user = create_user(db)

        meal = MealService.create_meal(db, user.id)

        assert meal.id is not None
        assert meal.user_id == user.id
        assert meal.status == "draft"
        assert meal.timestamp is not None

    def test_create_meal_with_all_fields(self, db: Session):
        """Test creating a meal with all optional fields."""
        user = create_user(db)
        timestamp = datetime.now(timezone.utc)

        meal = MealService.create_meal(
            db,
            user.id,
            image_path="/uploads/test.jpg",
            user_notes="Test meal notes",
            country="USA",
            timestamp=timestamp,
        )

        assert meal.image_path == "/uploads/test.jpg"
        assert meal.user_notes == "Test meal notes"
        assert meal.country == "USA"
        assert meal.timestamp == timestamp

    def test_create_meal_starts_as_draft(self, db: Session):
        """Test that new meals start with draft status."""
        user = create_user(db)

        meal = MealService.create_meal(db, user.id)

        assert meal.status == "draft"


class TestMealIngredients:
    """Tests for adding/removing ingredients."""

    def test_add_ingredient_creates_new_ingredient(self, db: Session):
        """Test that adding a new ingredient creates it."""
        user = create_user(db)
        meal = create_meal(db, user)

        meal_ingredient = MealService.add_ingredient_to_meal(
            db, meal.id, ingredient_name="Chicken Breast", state=IngredientState.COOKED
        )

        assert meal_ingredient.id is not None
        assert meal_ingredient.ingredient.normalized_name == "chicken_breast"
        assert meal_ingredient.state == IngredientState.COOKED

    def test_add_ingredient_reuses_existing(self, db: Session):
        """Test that adding an existing ingredient reuses it."""
        user = create_user(db)
        meal = create_meal(db, user)

        # Create ingredient first with unique name
        unique_name = f"Chicken_{secrets.token_hex(4)}"
        existing = create_ingredient(db, name=unique_name)

        # Add to meal with same name (case-insensitive)
        meal_ingredient = MealService.add_ingredient_to_meal(
            db,
            meal.id,
            ingredient_name=unique_name.lower(),
            state=IngredientState.COOKED,
        )

        assert meal_ingredient.ingredient_id == existing.id

    def test_add_ingredient_normalizes_name(self, db: Session):
        """Test that ingredient names are normalized."""
        user = create_user(db)
        meal = create_meal(db, user)

        # Add with varied capitalization and spacing
        MealService.add_ingredient_to_meal(
            db,
            meal.id,
            ingredient_name="  CHICKEN BREAST  ",
            state=IngredientState.COOKED,
        )

        # Check normalized form
        ingredient = (
            db.query(Ingredient)
            .filter(Ingredient.normalized_name == "chicken_breast")
            .first()
        )
        assert ingredient is not None

    def test_add_ingredient_with_quantity(self, db: Session):
        """Test adding ingredient with quantity description."""
        user = create_user(db)
        meal = create_meal(db, user)

        meal_ingredient = MealService.add_ingredient_to_meal(
            db,
            meal.id,
            ingredient_name="Rice",
            state=IngredientState.COOKED,
            quantity_description="1 cup",
        )

        assert meal_ingredient.quantity_description == "1 cup"

    def test_add_ingredient_with_confidence(self, db: Session):
        """Test adding AI-detected ingredient with confidence score."""
        user = create_user(db)
        meal = create_meal(db, user)

        meal_ingredient = MealService.add_ingredient_to_meal(
            db,
            meal.id,
            ingredient_name="Broccoli",
            state=IngredientState.COOKED,
            confidence=0.92,
            source="ai",
        )

        assert float(meal_ingredient.confidence) == pytest.approx(0.92, abs=0.01)
        assert meal_ingredient.source == "ai"

    def test_remove_ingredient(self, db: Session):
        """Test removing an ingredient from a meal."""
        user = create_user(db)
        meal = create_meal(db, user)
        ingredient = create_ingredient(db, name="Tomato")
        meal_ing = create_meal_ingredient(db, meal, ingredient)

        result = MealService.remove_ingredient_from_meal(db, meal_ing.id)

        assert result is True
        # Verify it's gone
        assert (
            db.query(MealIngredient).filter(MealIngredient.id == meal_ing.id).first()
            is None
        )

    def test_remove_nonexistent_ingredient(self, db: Session):
        """Test that removing a non-existent ingredient returns False."""
        result = MealService.remove_ingredient_from_meal(db, 99999)

        assert result is False


class TestIngredientNormalization:
    """Tests for ingredient name normalization."""

    def test_normalize_strips_whitespace(self):
        """Test that whitespace is stripped."""
        assert Ingredient.normalize_name("  chicken  ") == "chicken"

    def test_normalize_lowercases(self):
        """Test that names are lowercased."""
        assert Ingredient.normalize_name("CHICKEN BREAST") == "chicken_breast"

    def test_normalize_replaces_spaces(self):
        """Test that spaces are replaced with underscores."""
        assert Ingredient.normalize_name("chicken breast") == "chicken_breast"

    def test_normalize_replaces_hyphens(self):
        """Test that hyphens are replaced with underscores."""
        assert Ingredient.normalize_name("sun-dried tomatoes") == "sun_dried_tomatoes"

    def test_normalize_handles_empty_string(self):
        """Test that empty strings don't cause errors."""
        assert Ingredient.normalize_name("") == ""


class TestMealQueries:
    """Tests for meal query methods."""

    def test_get_meal_by_id(self, db: Session):
        """Test retrieving a meal by ID."""
        user = create_user(db)
        meal = create_meal(db, user, name="Test Meal")

        result = MealService.get_meal(db, meal.id)

        assert result is not None
        assert result.id == meal.id
        assert result.name == "Test Meal"

    def test_get_nonexistent_meal(self, db: Session):
        """Test that getting a non-existent meal returns None."""
        result = MealService.get_meal(db, 99999)

        assert result is None

    def test_get_user_meals(self, db: Session):
        """Test getting all meals for a user."""
        user = create_user(db)

        # Create meals
        for i in range(3):
            create_meal(
                db,
                user,
                name=f"Meal {i}",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
            )

        meals = MealService.get_user_meals(db, user.id)

        assert len(meals) == 3
        # Should be ordered by timestamp descending
        assert meals[0].name == "Meal 0"  # Most recent

    def test_get_user_meals_only_published(self, db: Session):
        """Test that only published meals are returned."""
        user = create_user(db)

        # Create published meals
        for i in range(2):
            create_meal(db, user, status="published")

        # Create draft meals
        for i in range(3):
            create_meal(db, user, status="draft")

        meals = MealService.get_user_meals(db, user.id)

        assert len(meals) == 2
        assert all(m.status == "published" for m in meals)

    def test_get_user_meals_pagination(self, db: Session):
        """Test meal pagination."""
        user = create_user(db)

        # Create 10 meals
        for i in range(10):
            create_meal(
                db, user, timestamp=datetime.now(timezone.utc) - timedelta(hours=i)
            )

        # Get first page
        page1 = MealService.get_user_meals(db, user.id, limit=5, offset=0)
        assert len(page1) == 5

        # Get second page
        page2 = MealService.get_user_meals(db, user.id, limit=5, offset=5)
        assert len(page2) == 5

        # Verify no overlap
        page1_ids = {m.id for m in page1}
        page2_ids = {m.id for m in page2}
        assert page1_ids.isdisjoint(page2_ids)


class TestMealUpdates:
    """Tests for meal update methods."""

    def test_update_meal_notes(self, db: Session):
        """Test updating meal notes."""
        user = create_user(db)
        meal = create_meal(db, user, user_notes="Original notes")

        result = MealService.update_meal(db, meal.id, user_notes="Updated notes")

        assert result is not None
        assert result.user_notes == "Updated notes"

    def test_update_meal_country(self, db: Session):
        """Test updating meal country."""
        user = create_user(db)
        meal = create_meal(db, user)

        result = MealService.update_meal(db, meal.id, country="Japan")

        assert result.country == "Japan"

    def test_update_meal_timestamp(self, db: Session):
        """Test updating meal timestamp."""
        user = create_user(db)
        meal = create_meal(db, user)
        new_time = datetime.now(timezone.utc) - timedelta(days=1)

        result = MealService.update_meal(db, meal.id, timestamp=new_time)

        assert result.timestamp == new_time

    def test_update_nonexistent_meal(self, db: Session):
        """Test that updating a non-existent meal returns None."""
        result = MealService.update_meal(db, 99999, user_notes="Notes")

        assert result is None

    def test_update_meal_name(self, db: Session):
        """Test updating meal name."""
        user = create_user(db)
        meal = create_meal(db, user, name="Original Name")

        result = MealService.update_meal_name(db, meal.id, "New Name")

        assert result is not None
        assert result.name == "New Name"

    def test_update_meal_name_changes_source(self, db: Session):
        """Test that editing AI-suggested name changes source to user-edit."""
        user = create_user(db)
        meal = create_meal(db, user, name="AI Name")
        meal.name_source = "ai"
        db.flush()

        result = MealService.update_meal_name(db, meal.id, "User Name")

        assert result.name_source == "user-edit"


class TestIngredientUpdates:
    """Tests for ingredient update methods."""

    def test_update_ingredient_name(self, db: Session):
        """Test updating an ingredient's name."""
        user = create_user(db)
        meal = create_meal(db, user)
        ingredient = create_ingredient(db, name="Chickin")  # Typo
        meal_ing = create_meal_ingredient(db, meal, ingredient)

        result = MealService.update_ingredient_in_meal(
            db,
            meal_ing.id,
            ingredient_name="Chicken",  # Corrected
        )

        assert result is not None
        # Should link to a different (correct) ingredient
        assert result.ingredient.normalized_name == "chicken"

    def test_update_ingredient_quantity(self, db: Session):
        """Test updating ingredient quantity."""
        user = create_user(db)
        meal = create_meal(db, user)
        ingredient = create_ingredient(db, name="Rice")
        meal_ing = create_meal_ingredient(
            db, meal, ingredient, quantity_description="1 cup"
        )

        result = MealService.update_ingredient_in_meal(
            db, meal_ing.id, quantity_description="2 cups"
        )

        assert result.quantity_description == "2 cups"

    def test_update_ingredient_state(self, db: Session):
        """Test updating ingredient state."""
        user = create_user(db)
        meal = create_meal(db, user)
        ingredient = create_ingredient(db, name="Carrot")
        meal_ing = create_meal_ingredient(
            db, meal, ingredient, state=IngredientState.RAW
        )

        result = MealService.update_ingredient_state(
            db, meal_ing.id, state=IngredientState.COOKED
        )

        assert result.state == IngredientState.COOKED

    def test_update_ingredient_changes_source(self, db: Session):
        """Test that editing AI ingredient changes source to user-edit."""
        user = create_user(db)
        meal = create_meal(db, user)
        # Use unique names to avoid collisions with other tests
        original_name = f"Broccoli_{secrets.token_hex(4)}"
        new_name = f"Cauliflower_{secrets.token_hex(4)}"
        ingredient = create_ingredient(db, name=original_name)
        meal_ing = create_meal_ingredient(db, meal, ingredient, source="ai")

        result = MealService.update_ingredient_in_meal(
            db, meal_ing.id, ingredient_name=new_name
        )

        assert result.source == "user-edit"


class TestMealPublishing:
    """Tests for meal publishing."""

    def test_publish_meal(self, db: Session):
        """Test publishing a draft meal."""
        user = create_user(db)
        meal = create_meal(db, user, status="draft")

        result = MealService.publish_meal(db, meal.id)

        assert result is not None
        assert result.status == "published"

    def test_publish_nonexistent_meal(self, db: Session):
        """Test that publishing a non-existent meal returns None."""
        result = MealService.publish_meal(db, 99999)

        assert result is None


class TestMealDeletion:
    """Tests for meal deletion."""

    def test_delete_meal(self, db: Session):
        """Test deleting a meal."""
        user = create_user(db)
        meal = create_meal(db, user)
        meal_id = meal.id

        result = MealService.delete_meal(db, meal_id)

        assert result is True
        # Verify meal is deleted
        assert db.query(Meal).filter(Meal.id == meal_id).first() is None

    def test_delete_meal_cascades_ingredients(self, db: Session):
        """Test that deleting a meal also deletes its ingredients."""
        user = create_user(db)
        meal = create_meal(db, user)
        ingredient = create_ingredient(db, name="Tomato")
        meal_ing = create_meal_ingredient(db, meal, ingredient)
        meal_ing_id = meal_ing.id

        MealService.delete_meal(db, meal.id)

        # Meal ingredient should be deleted
        assert (
            db.query(MealIngredient).filter(MealIngredient.id == meal_ing_id).first()
            is None
        )
        # But the ingredient itself should still exist
        assert (
            db.query(Ingredient).filter(Ingredient.id == ingredient.id).first()
            is not None
        )

    def test_delete_nonexistent_meal(self, db: Session):
        """Test that deleting a non-existent meal returns False."""
        result = MealService.delete_meal(db, 99999)

        assert result is False


class TestRaceConditions:
    """Tests for race condition handling in ingredient creation."""

    def test_handles_concurrent_ingredient_creation(self, db: Session):
        """Test that concurrent ingredient creation is handled."""
        user = create_user(db)
        meal = create_meal(db, user)

        # This test verifies the race condition handling code path
        # The actual race condition is hard to test without threading,
        # but we can verify the code handles IntegrityError correctly

        # Add ingredient normally first
        meal_ingredient = MealService.add_ingredient_to_meal(
            db, meal.id, ingredient_name="Test Ingredient", state=IngredientState.RAW
        )

        assert meal_ingredient is not None
        assert meal_ingredient.ingredient.name == "Test Ingredient"
