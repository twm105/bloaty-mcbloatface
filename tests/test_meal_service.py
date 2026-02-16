"""
Tests for MealService - specifically the duplicate_meal functionality.
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.meal_ingredient import IngredientState
from app.services.meal_service import meal_service
from tests.factories import (
    create_user,
    create_meal,
    create_ingredient,
    create_meal_ingredient,
)


class TestDuplicateMeal:
    """Tests for MealService.duplicate_meal()."""

    def test_duplicate_meal_copies_all_fields(self, db: Session):
        """Verify name, image_path, crop settings, country, user_notes are copied."""
        user = create_user(db)
        original = create_meal(
            db,
            user,
            name="Test Meal",
            country="USA",
            image_path="uploads/test.jpg",
            meal_image_crop_x=30.0,
            meal_image_crop_y=70.0,
            user_notes="This is a test note",
        )

        duplicate = meal_service.duplicate_meal(db, original.id, user.id)

        assert duplicate is not None
        assert duplicate.id != original.id
        assert duplicate.name == original.name
        assert duplicate.country == original.country
        assert duplicate.image_path == original.image_path
        assert duplicate.meal_image_crop_x == original.meal_image_crop_x
        assert duplicate.meal_image_crop_y == original.meal_image_crop_y
        assert duplicate.user_notes == original.user_notes

    def test_duplicate_meal_copies_ingredients(self, db: Session):
        """Verify all ingredients copied with correct state, quantity, source='copy'."""
        user = create_user(db)
        original = create_meal(db, user, name="Meal With Ingredients")

        # Add ingredients
        tomato = create_ingredient(db, name="Tomato")
        cheese = create_ingredient(db, name="Cheese")

        create_meal_ingredient(
            db,
            original,
            tomato,
            state=IngredientState.RAW,
            quantity_description="2 medium",
            source="ai",
        )
        create_meal_ingredient(
            db,
            original,
            cheese,
            state=IngredientState.PROCESSED,
            quantity_description="50g",
            source="manual",
        )

        db.refresh(original)

        duplicate = meal_service.duplicate_meal(db, original.id, user.id)

        assert duplicate is not None
        assert len(duplicate.meal_ingredients) == 2

        # Check ingredients are copied correctly
        dup_ingredients = {mi.ingredient.name: mi for mi in duplicate.meal_ingredients}

        assert "Tomato" in dup_ingredients
        assert dup_ingredients["Tomato"].state == IngredientState.RAW
        assert dup_ingredients["Tomato"].quantity_description == "2 medium"
        assert dup_ingredients["Tomato"].source == "copy"

        assert "Cheese" in dup_ingredients
        assert dup_ingredients["Cheese"].state == IngredientState.PROCESSED
        assert dup_ingredients["Cheese"].quantity_description == "50g"
        assert dup_ingredients["Cheese"].source == "copy"

    def test_duplicate_meal_sets_copied_from_id(self, db: Session):
        """Verify lineage tracking - copied_from_id points to original."""
        user = create_user(db)
        original = create_meal(db, user, name="Original Meal")

        duplicate = meal_service.duplicate_meal(db, original.id, user.id)

        assert duplicate is not None
        assert duplicate.copied_from_id == original.id
        assert duplicate.is_copy is True
        assert original.is_copy is False

    def test_duplicate_meal_uses_current_timestamp(self, db: Session):
        """Verify new timestamp, not original."""
        user = create_user(db)
        old_time = datetime.now(timezone.utc) - timedelta(days=7)
        original = create_meal(db, user, name="Old Meal", timestamp=old_time)

        before_duplicate = datetime.now(timezone.utc)
        duplicate = meal_service.duplicate_meal(db, original.id, user.id)
        after_duplicate = datetime.now(timezone.utc)

        assert duplicate is not None
        # Duplicate timestamp should be close to now, not the original time
        assert duplicate.timestamp != original.timestamp
        # Allow some tolerance for test execution time
        assert duplicate.timestamp.replace(tzinfo=timezone.utc) >= before_duplicate.replace(
            microsecond=0
        ) - timedelta(seconds=1)
        assert duplicate.timestamp.replace(tzinfo=timezone.utc) <= after_duplicate + timedelta(
            seconds=1
        )

    def test_duplicate_meal_sets_published_status(self, db: Session):
        """Verify immediately published (not draft)."""
        user = create_user(db)
        original = create_meal(db, user, name="Test Meal", status="published")

        duplicate = meal_service.duplicate_meal(db, original.id, user.id)

        assert duplicate is not None
        assert duplicate.status == "published"
        assert duplicate.name_source == "copy"

    def test_duplicate_meal_chain_copies(self, db: Session):
        """Verify duplicating a copy works correctly - still points to immediate source."""
        user = create_user(db)
        original = create_meal(db, user, name="Original")
        tomato = create_ingredient(db, name="Tomato")
        create_meal_ingredient(db, original, tomato, state=IngredientState.RAW)
        db.refresh(original)

        # First copy
        copy1 = meal_service.duplicate_meal(db, original.id, user.id)
        assert copy1 is not None
        assert copy1.copied_from_id == original.id

        # Second copy (copy of a copy)
        copy2 = meal_service.duplicate_meal(db, copy1.id, user.id)
        assert copy2 is not None
        assert copy2.copied_from_id == copy1.id  # Points to copy1, not original
        assert copy2.is_copy is True
        assert len(copy2.meal_ingredients) == 1

    def test_duplicate_meal_wrong_user_returns_none(self, db: Session):
        """Verify ownership check - returns None for another user's meal."""
        user1 = create_user(db, email="user1@example.com")
        user2 = create_user(db, email="user2@example.com")

        meal = create_meal(db, user1, name="User1's Meal")

        # User2 tries to duplicate User1's meal
        result = meal_service.duplicate_meal(db, meal.id, user2.id)

        assert result is None

    def test_duplicate_meal_not_found_returns_none(self, db: Session):
        """Verify returns None for non-existent meal."""
        user = create_user(db)

        result = meal_service.duplicate_meal(db, 999999, user.id)

        assert result is None

    def test_duplicate_meal_preserves_ingredient_confidence(self, db: Session):
        """Verify AI confidence scores are preserved in copies."""
        user = create_user(db)
        original = create_meal(db, user, name="AI Analyzed Meal")
        tomato = create_ingredient(db, name="Tomato")
        create_meal_ingredient(
            db,
            original,
            tomato,
            state=IngredientState.RAW,
            confidence=0.95,
            source="ai",
        )
        db.refresh(original)

        duplicate = meal_service.duplicate_meal(db, original.id, user.id)

        assert duplicate is not None
        assert len(duplicate.meal_ingredients) == 1
        assert float(duplicate.meal_ingredients[0].confidence) == 0.95


class TestCountMealsWithImage:
    """Tests for MealService.count_meals_with_image()."""

    def test_count_meals_with_image_single_meal(self, db: Session):
        """Verify count is 1 for a single meal with image."""
        user = create_user(db)
        create_meal(db, user, name="Meal with image", image_path="/uploads/test.jpg")

        count = meal_service.count_meals_with_image(db, "/uploads/test.jpg")

        assert count == 1

    def test_count_meals_with_image_shared_image(self, db: Session):
        """Verify count reflects all meals sharing an image (e.g., duplicates)."""
        user = create_user(db)
        original = create_meal(
            db, user, name="Original", image_path="/uploads/shared.jpg"
        )

        # Create duplicate that shares the image
        duplicate = meal_service.duplicate_meal(db, original.id, user.id)
        assert duplicate is not None
        assert duplicate.image_path == original.image_path

        count = meal_service.count_meals_with_image(db, "/uploads/shared.jpg")

        assert count == 2

    def test_count_meals_with_image_no_matches(self, db: Session):
        """Verify count is 0 for image path with no meals."""
        count = meal_service.count_meals_with_image(db, "/uploads/nonexistent.jpg")

        assert count == 0

    def test_count_meals_with_image_different_images(self, db: Session):
        """Verify count only includes meals with the specific image path."""
        user = create_user(db)
        create_meal(db, user, name="Meal A", image_path="/uploads/image_a.jpg")
        create_meal(db, user, name="Meal B", image_path="/uploads/image_b.jpg")
        create_meal(db, user, name="Meal C", image_path="/uploads/image_a.jpg")

        count_a = meal_service.count_meals_with_image(db, "/uploads/image_a.jpg")
        count_b = meal_service.count_meals_with_image(db, "/uploads/image_b.jpg")

        assert count_a == 2
        assert count_b == 1
